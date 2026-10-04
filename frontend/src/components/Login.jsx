import { useState } from 'react'
import { apiFetch } from '../api/client'
import LogoUAL from './LogoUAL'

// El backend ya explica en español la cuenta sin confirmar o desactivada
// (403). Solo "Credenciales incorrectas" (400) se dice de forma más útil, y los
// errores de validación de FastAPI llegan como lista.
function mensajeDeError(resp, data, esRegistro) {
  if (!esRegistro && resp.status === 400) return 'El correo o la contraseña no son correctos.';
  if (Array.isArray(data.detail)) return data.detail.map(e => e.msg).join(', ');
  return data.detail || 'No se pudo completar la operación.';
}

export default function Login({ alLoguear }) {
  const [esRegistro,        setEsRegistro]        = useState(false);
  const [email,             setEmail]             = useState('');
  const [password_hash,     setPassword]          = useState('');
  const [nombre,            setNombre]            = useState('');
  const [error,             setError]             = useState('');
  const [pendienteVerificar, setPendienteVerificar] = useState(false);

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
        setError(mensajeDeError(resp, data, esRegistro));
      }
    } catch {
      setError('No se puede conectar con el servidor. Comprueba que la plataforma está en marcha.');
    }
  };

  return (
    <div className="login-pagina">
      <div className="login-franja" />
      <main className="login-wrapper">
        <div className="login-card">
          <LogoUAL className="login-logo" claseTexto="login-logo-texto" />

          {pendienteVerificar ? (
            <>
              <h1>Confirma tu correo</h1>
              <p className="texto-secundario">
                Te hemos enviado un enlace a <strong>{email}</strong>. Ábrelo para activar
                tu cuenta y después inicia sesión. Si no lo ves, mira en la carpeta de spam.
              </p>
              <button
                className="btn-primary"
                onClick={() => { setPendienteVerificar(false); setEsRegistro(false); }}
              >
                Volver a iniciar sesión
              </button>
            </>
          ) : (
            <>
              <h1>{esRegistro ? 'Crear cuenta' : 'Iniciar sesión'}</h1>
              <p className="texto-secundario">Plataforma de cribado virtual</p>

              <form onSubmit={manejarSubmit} className="login-form">
                {esRegistro && (
                  <>
                    <label htmlFor="login-nombre">Nombre</label>
                    <input id="login-nombre" autoComplete="name"
                           onChange={e => setNombre(e.target.value)} required />
                  </>
                )}
                <label htmlFor="login-email">Correo electrónico</label>
                <input id="login-email" type="email" autoComplete="email"
                       onChange={e => setEmail(e.target.value)} required />
                <label htmlFor="login-password">Contraseña</label>
                <input id="login-password" type="password"
                       autoComplete={esRegistro ? 'new-password' : 'current-password'}
                       onChange={e => setPassword(e.target.value)} required />
                <button type="submit" className="btn-primary">
                  {esRegistro ? 'Crear cuenta' : 'Iniciar sesión'}
                </button>
              </form>

              {error && <p className="error-msg" role="alert">{error}</p>}

              <p className="login-alterno">
                {esRegistro ? '¿Ya tienes cuenta? ' : '¿No tienes cuenta? '}
                <button className="btn-enlace" onClick={() => { setEsRegistro(!esRegistro); setError(''); }}>
                  {esRegistro ? 'Inicia sesión' : 'Crea una'}
                </button>
              </p>
            </>
          )}
        </div>
      </main>
      <p className="login-pie">Trabajo Fin de Grado · Universidad de Almería</p>
    </div>
  );
}
