import { useState } from 'react'

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
      const resp = await fetch(`http://localhost:8000${ruta}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await resp.json();
      if (resp.ok) {
        if (esRegistro) {
          // Registro OK → mostrar pantalla de "revisa tu correo"
          setPendienteVerificar(true);
        } else {
          alLoguear(data);
        }
      } else {
        const msg = Array.isArray(data.detail)
          ? data.detail.map(e => e.msg).join(', ')
          : (data.detail || 'Error en la operación');
        setError(msg);
      }
    } catch { setError('Servidor no disponible'); }
  };

  // Pantalla de confirmación pendiente
  if (pendienteVerificar) {
    return (
      <div className="login-wrapper">
        <div className="login-card" style={{ textAlign: 'center' }}>
          <div className="login-icono">📧</div>
          <h2 style={{ color: '#27ae60' }}>¡Revisa tu correo!</h2>
          <p style={{ color: '#555', lineHeight: 1.6, margin: '12px 0 20px' }}>
            Te hemos enviado un enlace de confirmación a <strong>{email}</strong>.
            <br />Haz clic en él para activar tu cuenta y poder iniciar sesión.
          </p>
          <p style={{ fontSize: '12px', color: '#999' }}>
            ¿No ha llegado? Revisa la carpeta de spam.
          </p>
          <button
            className="btn-toggle"
            style={{ marginTop: '20px' }}
            onClick={() => { setPendienteVerificar(false); setEsRegistro(false); }}
          >
            Volver al inicio de sesión
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="login-wrapper">
      <div className="login-card">
        <div className="login-icono">🧬</div>
        <h2>{esRegistro ? 'Crear Cuenta' : 'Iniciar Sesión'}</h2>
        <form onSubmit={manejarSubmit} className="login-form">
          {esRegistro && <input placeholder="Nombre" onChange={e => setNombre(e.target.value)} required />}
          <input placeholder="Email" type="email" onChange={e => setEmail(e.target.value)} required />
          <input placeholder="Contraseña" type="password" onChange={e => setPassword(e.target.value)} required />
          <button type="submit" className="btn-primary">
            {esRegistro ? 'Registrarse' : 'Entrar'}
          </button>
        </form>
        {error && <p className="error-msg">{error}</p>}
        <button onClick={() => { setEsRegistro(!esRegistro); setError(''); }} className="btn-toggle">
          {esRegistro ? '¿Ya tienes cuenta? Entra' : '¿No tienes cuenta? Regístrate'}
        </button>
      </div>
    </div>
  );
}