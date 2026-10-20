import { useState } from 'react'
import { apiFetch } from '../api/client'
import { textoDetalle } from '../utils/mensajes'
import { useIdioma } from '../hooks/useIdioma'

// «Elige una contraseña nueva» (spec 011, R6): lo que se ve al abrir el
// enlace del correo. Va dentro de la tarjeta del login.
export default function NuevaContrasena({ token, alTerminar, alPedirOtro }) {
  const { t } = useIdioma()
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
      setError(t('nueva.no_coinciden'))
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
        setError(textoDetalle(data.detail) || t('comun.error_generico'))
      }
    } catch {
      setError(t('comun.sin_conexion'))
    } finally {
      setEnviando(false)
    }
  }

  if (cambiada) {
    return (
      <>
        <h1>{t('nueva.cambiada')}</h1>
        <p className="texto-secundario" role="status">{t('nueva.ya_puedes')}</p>
        <button className="btn-primary" onClick={alTerminar}>{t('nueva.ir_login')}</button>
      </>
    )
  }

  if (enlaceNoValido) {
    return (
      <>
        <h1>{t('nueva.enlace_no_sirve')}</h1>
        <p className="error-msg" role="alert">{error}</p>
        <button className="btn-primary" onClick={alPedirOtro}>{t('nueva.pedir_otro')}</button>
      </>
    )
  }

  return (
    <>
      <h1>{t('nueva.titulo')}</h1>
      <p className="texto-secundario">{t('nueva.minimo')}</p>
      <form onSubmit={enviar} className="login-form">
        <label htmlFor="nueva-password">{t('nueva.nueva')}</label>
        <input id="nueva-password" type="password" autoComplete="new-password"
               minLength={8} maxLength={128} required
               value={password} onChange={e => setPassword(e.target.value)} />
        <label htmlFor="nueva-password-repetida">{t('nueva.repite')}</label>
        <input id="nueva-password-repetida" type="password" autoComplete="new-password"
               minLength={8} maxLength={128} required
               value={repetida} onChange={e => setRepetida(e.target.value)} />
        <button type="submit" className="btn-primary" disabled={enviando}>
          {enviando ? t('comun.guardando') : t('nueva.cambiar')}
        </button>
      </form>
      {error && <p className="error-msg" role="alert">{error}</p>}
    </>
  )
}
