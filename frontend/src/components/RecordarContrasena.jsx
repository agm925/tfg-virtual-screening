import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api/client'
import { textoDetalle } from '../utils/mensajes'
import TextoConFormato from './TextoConFormato'
import { useIdioma } from '../hooks/useIdioma'
import '../styles/RecordarContrasena.css'

// «¿Has olvidado tu contraseña?» (spec 011, R1). Mismo patrón que
// PreguntaVisibilidad: <dialog> con showModal, que ya hace el diálogo modal,
// lo cierra con Escape y no deja escapar el foco.
export default function RecordarContrasena({ abierto, emailInicial, alCerrar }) {
  const { t } = useIdioma()
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
        // ya llegan explicados desde el backend, en el idioma de la interfaz.
        const data = await resp.json().catch(() => ({}))
        setError(textoDetalle(data.detail) || t('comun.error_generico'))
      }
    } catch {
      setError(t('comun.sin_conexion'))
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
      <h3 id="recordar-contrasena-titulo">{t('recordar.titulo')}</h3>

      {enviadoA ? (
        <>
          <p role="status">
            <TextoConFormato texto={t('recordar.enviado', { email: `**${enviadoA}**` })} />
          </p>
          <button type="button" className="btn-primary" onClick={alCerrar}>{t('comun.cerrar')}</button>
        </>
      ) : (
        <form onSubmit={enviar} className="login-form">
          <p className="texto-secundario">
            {t('recordar.explicacion')}
          </p>
          <label htmlFor="recordar-email">{t('comun.correo')}</label>
          <input id="recordar-email" ref={campo} type="email" autoComplete="email" required
                 value={email} onChange={e => setEmail(e.target.value)} />
          {error && <p className="error-msg" role="alert">{error}</p>}
          <div className="recordar-contrasena-botones">
            <button type="button" className="btn-secundario" onClick={alCerrar}>{t('comun.cancelar')}</button>
            <button type="submit" className="btn-primary" disabled={enviando}>
              {enviando ? t('recordar.enviando') : t('recordar.enviar')}
            </button>
          </div>
        </form>
      )}
    </dialog>
  )
}
