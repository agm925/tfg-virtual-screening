import { useState } from 'react'
import { apiFetch } from '../api/client'
import LogoUAL from './LogoUAL'
import SelectorIdioma from './SelectorIdioma'
import TextoConFormato from './TextoConFormato'
import { useIdioma } from '../hooks/useIdioma'
import RecordarContrasena from './RecordarContrasena'
import NuevaContrasena from './NuevaContrasena'
import { textoDetalle } from '../utils/mensajes'

// El backend ya explica en español la cuenta sin confirmar o desactivada
// (403). Solo "Credenciales incorrectas" (400) se dice de forma más útil, y los
// errores de validación de FastAPI llegan como lista.
function mensajeDeError(resp, data, esRegistro, t) {
  if (!esRegistro && resp.status === 400) return t('login.credenciales');
  return textoDetalle(data.detail) || t('comun.error_generico');
}

export default function Login({ alLoguear, tokenRestablecer, alTerminarRestablecer }) {
  const { t } = useIdioma();
  const [esRegistro,        setEsRegistro]        = useState(false);
  const [email,             setEmail]             = useState('');
  const [password_hash,     setPassword]          = useState('');
  const [nombre,            setNombre]            = useState('');
  const [error,             setError]             = useState('');
  const [pendienteVerificar, setPendienteVerificar] = useState(false);
  const [recordarAbierto,   setRecordarAbierto]   = useState(false);

  const manejarSubmit = async (e) => {
    e.preventDefault();
    setError('');
    const ruta = esRegistro ? '/registro' : '/login';
    const body = esRegistro ? { nombre, email, password_hash } : { email, password_hash };

    try {
      const resp = await apiFetch(ruta, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await resp.json();
      if (resp.ok) {
        if (esRegistro) setPendienteVerificar(true);
        else alLoguear(data);
      } else {
        setError(mensajeDeError(resp, data, esRegistro, t));
      }
    } catch {
      setError(t('comun.sin_conexion'));
    }
  };

  return (
    <div className="login-pagina">
      <div className="login-franja" />
      {/* Arriba a la derecha, como en la cabecera (spec 014, R3). */}
      <SelectorIdioma className="login-idioma" />
      <main className="login-wrapper">
        <div className="login-card">
          <LogoUAL className="login-logo" claseTexto="login-logo-texto" />

          {tokenRestablecer ? (
            <NuevaContrasena
              token={tokenRestablecer}
              alTerminar={() => alTerminarRestablecer(true)}
              alPedirOtro={() => { alTerminarRestablecer(false); setRecordarAbierto(true); }}
            />
          ) : pendienteVerificar ? (
            <>
              <h1>{t('login.confirma_titulo')}</h1>
              <p className="texto-secundario">
                <TextoConFormato texto={t('login.confirma_texto', { email: `**${email}**` })} />
              </p>
              <button
                className="btn-primary"
                onClick={() => { setPendienteVerificar(false); setEsRegistro(false); }}
              >
                {t('login.volver')}
              </button>
            </>
          ) : (
            <>
              <h1>{esRegistro ? t('login.crear_cuenta') : t('login.iniciar_sesion')}</h1>
              <p className="texto-secundario">{t('login.subtitulo')}</p>

              <form onSubmit={manejarSubmit} className="login-form">
                {esRegistro && (
                  <>
                    <label htmlFor="login-nombre">{t('login.nombre')}</label>
                    <input id="login-nombre" autoComplete="name"
                           onChange={e => setNombre(e.target.value)} required />
                  </>
                )}
                <label htmlFor="login-email">{t('comun.correo')}</label>
                <input id="login-email" type="email" autoComplete="email"
                       onChange={e => setEmail(e.target.value)} required />
                <label htmlFor="login-password">{t('login.contrasena')}</label>
                <input id="login-password" type="password"
                       autoComplete={esRegistro ? 'new-password' : 'current-password'}
                       onChange={e => setPassword(e.target.value)} required />
                {!esRegistro && (
                  <button type="button" className="btn-enlace login-olvido"
                          onClick={() => setRecordarAbierto(true)}>
                    {t('recordar.titulo')}
                  </button>
                )}
                <button type="submit" className="btn-primary">
                  {esRegistro ? t('login.crear_cuenta') : t('login.iniciar_sesion')}
                </button>
              </form>

              {error && <p className="error-msg" role="alert">{error}</p>}

              <p className="login-alterno">
                {esRegistro ? t('login.ya_tienes') : t('login.no_tienes')}{' '}
                <button className="btn-enlace" onClick={() => { setEsRegistro(!esRegistro); setError(''); }}>
                  {esRegistro ? t('login.inicia') : t('login.crea_una')}
                </button>
              </p>
            </>
          )}
        </div>
      </main>
      <RecordarContrasena
        abierto={recordarAbierto}
        emailInicial={email}
        alCerrar={() => setRecordarAbierto(false)}
      />
      <p className="login-pie">{t('cabecera.universidad')}</p>
    </div>
  );
}
