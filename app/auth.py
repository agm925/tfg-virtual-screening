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
        "iat": ahora,
        "exp": ahora + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


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
    return usuario


def es_admin(usuario: models.Usuario) -> bool:
    return bool(usuario.rol and usuario.rol.value == "admin")


def requiere_rol(*roles_permitidos: str):
    """
    Fabrica de dependencias: `Depends(requiere_rol("admin", "desarrollador"))`
    exige que el usuario autenticado tenga uno de los roles indicados,
    ademas de estar autenticado. Da el efecto real sobre el campo `rol`
    del modelo de datos que antes no tenia ninguna consecuencia.
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
