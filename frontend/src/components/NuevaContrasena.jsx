import { useState } from 'react'
import { apiFetch } from '../api/client'
import { textoDetalle } from '../utils/mensajes'

// «Elige una contraseña nueva» (spec 011, R6): lo que se ve al abrir el
// enlace del correo. Va dentro de la tarjeta del login.
export default function NuevaContrasena({ token, alTerminar, alPedirOtro }) {
  const [password, setPassword] = useState('')
  const [repetida, setRepetida] = useState('')
  const [error, setError] = useState('')
  const [enlaceNoValido, setEnlaceNoValido] = useState(false)
  const [cambiada, setCambiada] = useState(false)
  const [enviando, setEnviando] = useState(false)

  const enviar = async (e) => {
    e.preventDefault()
    setError('')
    if (password !== repetida) {
      setError('Las contraseñas no coinciden.')
      return
    }
    setEnviando(true)
    try {
      const resp = await apiFetch('/restablecer-contrasena', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, password }),
      })
      if (resp.ok) {
        setCambiada(true)
      } else {
        const data = await resp.json().catch(() => ({}))
        // 400: el enlace ya no sirve, y escribir otra contraseña no lo arregla.
        setEnlaceNoValido(resp.status === 400)
        setError(textoDetalle(data.detail) || 'No se pudo completar la operación. Inténtalo de nuevo.')
      }
    } catch {
      setError('No se puede conectar con el servidor. Comprueba que la plataforma está en marcha.')
    } finally {
      setEnviando(false)
    }
  }

  if (cambiada) {
    return (
      <>
        <h1>Contraseña cambiada</h1>
        <p className="texto-secundario" role="status">Ya puedes iniciar sesión con tu contraseña nueva.</p>
        <button className="btn-primary" onClick={alTerminar}>Ir a iniciar sesión</button>
      </>
    )
  }

  if (enlaceNoValido) {
    return (
      <>
        <h1>Este enlace ya no sirve</h1>
        <p className="error-msg" role="alert">{error}</p>
        <button className="btn-primary" onClick={alPedirOtro}>Pedir otro enlace</button>
      </>
    )
  }

  return (
    <>
      <h1>Elige una contraseña nueva</h1>
      <p className="texto-secundario">Al menos 8 caracteres.</p>
      <form onSubmit={enviar} className="login-form">
        <label htmlFor="nueva-password">Nueva contraseña</label>
        <input id="nueva-password" type="password" autoComplete="new-password"
               minLength={8} maxLength={128} required
               value={password} onChange={e => setPassword(e.target.value)} />
        <label htmlFor="nueva-password-repetida">Repite la contraseña</label>
        <input id="nueva-password-repetida" type="password" autoComplete="new-password"
               minLength={8} maxLength={128} required
               value={repetida} onChange={e => setRepetida(e.target.value)} />
        <button type="submit" className="btn-primary" disabled={enviando}>
          {enviando ? 'Guardando…' : 'Cambiar contraseña'}
        </button>
      </form>
      {error && <p className="error-msg" role="alert">{error}</p>}
    </>
  )
}
