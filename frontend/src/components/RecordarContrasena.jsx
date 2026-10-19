import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api/client'
import { textoDetalle } from '../utils/mensajes'
import '../styles/RecordarContrasena.css'

// «¿Has olvidado tu contraseña?» (spec 011, R1). Mismo patrón que
// PreguntaVisibilidad: <dialog> con showModal, que ya hace el diálogo modal,
// lo cierra con Escape y no deja escapar el foco.
export default function RecordarContrasena({ abierto, emailInicial, alCerrar }) {
  const ref = useRef()
  const campo = useRef()
  const [email, setEmail] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [enviadoA, setEnviadoA] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const dialogo = ref.current
    if (!dialogo) return
    if (abierto && !dialogo.open) {
      // Cada vez que se abre empieza de cero, con lo que ya se escribió en
      // el login para no tener que repetirlo.
      setEmail(emailInicial || '')
      setEnviadoA(null)
      setError('')
      dialogo.showModal()
      // Aquí y no con autoFocus: React no lo escribe en el HTML y showModal
      // no lo vería.
      campo.current?.focus()
    }
    if (!abierto && dialogo.open) dialogo.close()
  }, [abierto, emailInicial])

  const enviar = async (e) => {
    e.preventDefault()
    setError('')
    setEnviando(true)
    try {
      const resp = await apiFetch('/recuperar-contrasena', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      if (resp.ok) {
        setEnviadoA(email)
      } else {
        // 404 (no existe), 429 (demasiadas) y 503 (el correo no ha salido)
        // ya llegan explicados en español desde el backend.
        const data = await resp.json().catch(() => ({}))
        setError(textoDetalle(data.detail) || 'No se pudo completar la operación. Inténtalo de nuevo.')
      }
    } catch {
      setError('No se puede conectar con el servidor. Comprueba que la plataforma está en marcha.')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <dialog
      ref={ref}
      className="recordar-contrasena"
      aria-labelledby="recordar-contrasena-titulo"
      onCancel={e => { e.preventDefault(); alCerrar() }}
    >
      <h3 id="recordar-contrasena-titulo">¿Has olvidado tu contraseña?</h3>

      {enviadoA ? (
        <>
          <p role="status">
            Te hemos enviado un enlace a <strong>{enviadoA}</strong>. Caduca en 1 hora.
            Si no lo ves, mira en la carpeta de spam.
          </p>
          <button type="button" className="btn-primary" onClick={alCerrar}>Cerrar</button>
        </>
      ) : (
        <form onSubmit={enviar} className="login-form">
          <p className="texto-secundario">
            Escribe el correo de tu cuenta y te enviaremos un enlace para elegir una contraseña nueva.
          </p>
          <label htmlFor="recordar-email">Correo electrónico</label>
          <input id="recordar-email" ref={campo} type="email" autoComplete="email" required
                 value={email} onChange={e => setEmail(e.target.value)} />
          {error && <p className="error-msg" role="alert">{error}</p>}
          <div className="recordar-contrasena-botones">
            <button type="button" className="btn-secundario" onClick={alCerrar}>Cancelar</button>
            <button type="submit" className="btn-primary" disabled={enviando}>
              {enviando ? 'Enviando…' : 'Enviar enlace'}
            </button>
          </div>
        </form>
      )}
    </dialog>
  )
}
