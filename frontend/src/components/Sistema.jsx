import { useState, useEffect, useRef } from 'react'
import { apiFetch } from '../api/client'

const POLL_MS = 8000

const Tarjeta = ({ titulo, children }) => (
  <div style={{
    background: 'white', borderRadius: '12px', padding: '20px',
    boxShadow: '0 2px 10px rgba(0,0,0,0.07)',
  }}>
    <h3 style={{ margin: '0 0 14px', color: '#2c3e50', fontSize: '16px' }}>{titulo}</h3>
    {children}
  </div>
)

const Metrica = ({ label, valor, color }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: '14px' }}>
    <span style={{ color: '#666' }}>{label}</span>
    <strong style={{ color: color || '#2c3e50' }}>{valor}</strong>
  </div>
)

export default function Sistema() {
  const [estado, setEstado] = useState(null)
  const [error, setError] = useState(null)
  const [cargando, setCargando] = useState(true)
  const intervalRef = useRef(null)

  const cargar = async () => {
    try {
      const resp = await apiFetch('/sistema/estado')
      if (resp.ok) {
        setEstado(await resp.json())
        setError(null)
      } else if (resp.status === 403) {
        setError('Tu rol no tiene permiso para ver esta página.')
      } else {
        setError('No se pudo consultar el estado del sistema.')
      }
    } catch {
      setError('Error de conexión con la API.')
    } finally {
      setCargando(false)
    }
  }

  useEffect(() => {
    cargar()
    intervalRef.current = setInterval(cargar, POLL_MS)
    return () => clearInterval(intervalRef.current)
  }, [])

  if (cargando) return <div className="seccion-wrapper"><p>⏳ Cargando estado del sistema…</p></div>
  if (error) return <div className="seccion-wrapper"><p className="error-msg">❌ {error}</p></div>
  if (!estado) return null

  const { servidor, cola, peticiones, workflows, usuarios } = estado

  return (
    <div className="seccion-wrapper">
      <h2>🛠️ Estado del sistema</h2>
      <p className="seccion-subtitulo">
        Hora del servidor: {new Date(servidor.hora_utc).toLocaleString('es-ES')} ·
        {' '}Modo de ejecución: <strong>{servidor.modo_ejecucion}</strong> ·
        {' '}Se actualiza sola cada {POLL_MS / 1000}s
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '20px', marginTop: '20px' }}>

        <Tarjeta titulo="⚙️ Cola de tareas (Celery)">
          {cola.disponible ? (
            <>
              <Metrica label="Workers conectados" valor={cola.workers_conectados} color={cola.workers_conectados > 0 ? '#27ae60' : '#c0392b'} />
              <Metrica label="Tareas ejecutándose ahora" valor={cola.tareas_en_ejecucion} />
              <Metrica label="worker_concurrency configurado" valor={cola.worker_concurrency_configurado} />
            </>
          ) : (
            <p className="error-msg" style={{ margin: 0 }}>❌ No se pudo consultar Celery/Redis: {cola.error}</p>
          )}
        </Tarjeta>

        <Tarjeta titulo="🔬 Peticiones">
          <Metrica label="Total" valor={peticiones.total} />
          <Metrica label="Pendientes" valor={peticiones.pendientes} color="#e67e22" />
          <Metrica label="Procesando" valor={peticiones.procesando} color="#2980b9" />
          <Metrica label="Completadas" valor={peticiones.completadas} color="#27ae60" />
          <Metrica label="Con error" valor={peticiones.error} color="#c0392b" />
        </Tarjeta>

        <Tarjeta titulo="🔧 Workflows">
          <Metrica label="Workflows creados" valor={workflows.total} />
          <Metrica label="Ejecuciones totales" valor={workflows.ejecuciones_total} />
          <Metrica label="Ejecuciones activas" valor={workflows.ejecuciones_activas} color="#2980b9" />
          <Metrica label="Ejecuciones completadas" valor={workflows.ejecuciones_completadas} color="#27ae60" />
          <Metrica label="Ejecuciones con error" valor={workflows.ejecuciones_error} color="#c0392b" />
        </Tarjeta>

        <Tarjeta titulo="👤 Usuarios">
          <Metrica label="Registrados" valor={usuarios.total} />
          <Metrica label="Con email verificado" valor={usuarios.verificados} color="#27ae60" />
        </Tarjeta>

      </div>
    </div>
  )
}
