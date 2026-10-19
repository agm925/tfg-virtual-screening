"""
Autenticacion y autorizacion: hashing de contraseñas, emision/verificacion
de JWT, y dependencias de FastAPI para proteger endpoints por identidad y
por rol.

Sustituye el modelo anterior (el frontend guardaba el objeto de usuario
completo en localStorage, sin expiracion, y varios endpoints confiaban
ciegamente en un `usuario_id` que el propio cliente enviaba por query/form)
por tokens firmados con expiracion: el `usuario_id` de un recurso se lee
del token verificado en el servidor, nunca de un parametro que el cliente
pueda manipular.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import secrets

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app import models
from app.config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET_KEY
from app.database import SessionLocal

_bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def crear_access_token(usuario: models.Usuario) -> str:
    """Genera un JWT firmado (HS256) con el id, email y rol del usuario, y
    una fecha de expiracion (JWT_EXPIRE_MINUTES, por defecto 24h)."""
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": str(usuario.id),
        "email": usuario.email,
        "rol": usuario.rol.value if usuario.rol else "biologo",
        # Con decimales, no en segundos enteros (PyJWT los acepta y el RFC
        # 7519 tambien): obtener_usuario_actual lo compara con el momento del
        # ultimo cambio de contraseña, y un token emitido en el mismo segundo
        # pero ANTES del cambio tiene que dejar de valer.
        "iat": ahora.timestamp(),
        "exp": ahora + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


# «¿Has olvidado tu contraseña?» (spec 011): el enlace del correo vale una hora.
VALIDEZ_ENLACE_RESTABLECER = timedelta(hours=1)


def _hash_token_restablecer(token: str) -> str:
    # SHA-256 sin sal basta (no bcrypt): el token son 256 bits aleatorios, no
    # una contraseña que se pueda adivinar por diccionario, y asi se puede
    # buscar la fila por igualdad.
    return hashlib.sha256(token.encode()).hexdigest()


def crear_token_restablecer(usuario: models.Usuario) -> str:
    """
    Genera el token del enlace y guarda en el usuario SOLO su hash y su
    caducidad (el commit lo hace quien llama). Un token nuevo sustituye al
    anterior, que deja de servir. Devuelve el token en claro, para el correo.
    """
    token = secrets.token_urlsafe(32)
    usuario.token_restablecer = _hash_token_restablecer(token)
    usuario.token_restablecer_expira = datetime.utcnow() + VALIDEZ_ENLACE_RESTABLECER
    return token


def usuario_por_token_restablecer(db: Session, token: str):
    """El usuario de un enlace que sigue valiendo, o None si es inventado,
    ya usado, sustituido por otro, caducado o de una cuenta desactivada."""
    usuario = db.query(models.Usuario).filter(
        models.Usuario.token_restablecer == _hash_token_restablecer(token)
    ).first()
    if (usuario is None or not usuario.activo
            or usuario.token_restablecer_expira is None
            or usuario.token_restablecer_expira < datetime.utcnow()):
        return None
    return usuario


def restablecer_password(usuario: models.Usuario, nueva: str) -> None:
    """
    Guarda la contraseña nueva y gasta el enlace (el commit lo hace quien
    llama). La cuenta queda confirmada: quien abre el enlace demuestra que el
    correo es suyo. Y las sesiones anteriores dejan de valer (ver
    obtener_usuario_actual).
    """
    usuario.password_hash = hash_password(nueva)
    usuario.token_restablecer = None
    usuario.token_restablecer_expira = None
    usuario.email_verificado = True
    usuario.token_verificacion = None
    usuario.password_cambiada_en = datetime.utcnow()


def _decodificar_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión ha caducado. Vuelve a iniciar sesión.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de sesión inválido.",
        )


def _get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def obtener_usuario_actual(
    credenciales: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: Session = Depends(_get_db),
) -> models.Usuario:
    """
    Dependencia de FastAPI: extrae y valida el JWT de la cabecera
    `Authorization: Bearer <token>`, y devuelve el Usuario correspondiente
    ya cargado de la base de datos (para reflejar cambios de rol o
    verificacion posteriores a la emision del token).
    """
    if credenciales is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado. Falta la cabecera Authorization: Bearer <token>.",
        )
    payload = _decodificar_token(credenciales.credentials)
    usuario_id = payload.get("sub")
    usuario = db.query(models.Usuario).filter(models.Usuario.id == int(usuario_id)).first()
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado.")
    # La cuenta desactivada se rechaza AQUI, y no solo en el login, porque el
    # token ya emitido sigue siendo criptograficamente valido hasta que caduca
    # --JWT_EXPIRE_MINUTES son 1440 por defecto, un dia entero--. Comprobarlo
    # solo al iniciar sesion dejaria a un usuario recien desactivado trabajando
    # con normalidad durante 24 horas, que es justo lo contrario de lo que el
    # administrador acaba de pedir. El usuario ya se recarga de la base en cada
    # peticion (ver el docstring), asi que el coste es nulo.
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta cuenta está desactivada. Contacta con un administrador.",
        )
    # Cambiar la contraseña cierra las sesiones abiertas con la anterior
    # (spec 011): si alguien tenia una robada, la pierde.
    if usuario.password_cambiada_en is not None:
        cambiada = usuario.password_cambiada_en.replace(tzinfo=timezone.utc).timestamp()
        if payload.get("iat", 0) < cambiada:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="La contraseña ha cambiado. Vuelve a iniciar sesión.",
            )
    return usuario


def es_admin(usuario: models.Usuario) -> bool:
    return bool(usuario.rol and usuario.rol.value == "admin")


def requiere_rol(*roles_permitidos: str):
    """
    Fabrica de dependencias: `Depends(requiere_rol("admin"))` exige que el
    usuario autenticado tenga uno de los roles indicados, ademas de estar
    autenticado. Da el efecto real sobre el campo `rol` del modelo de datos
    que antes no tenia ninguna consecuencia.

    Con solo dos roles (ver models.RolUsuario) el unico uso real es
    `requiere_rol("admin")`, reservado para la administracion de la
    plataforma: todo lo cientifico esta abierto a cualquier usuario
    autenticado y no debe protegerse con esta dependencia.
    """
    def _verificar(usuario: models.Usuario = Depends(obtener_usuario_actual)) -> models.Usuario:
        rol_actual = usuario.rol.value if usuario.rol else "biologo"
        if rol_actual not in roles_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Esta operación requiere el rol: {', '.join(roles_permitidos)}.",
            )
        return usuario
    return _verificar
