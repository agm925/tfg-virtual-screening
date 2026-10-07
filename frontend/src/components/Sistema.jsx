import { useState, useEffect } from 'react'
import { apiFetch } from '../api/client'
import Icono from './Icono'
import { formatFecha } from '../utils/ficheros'
import { errorDeRespuesta, mensajeError } from '../utils/mensajes'
import '../styles/Sistema.css'

const POLL_MS = 8000

// Donde se ejecutan los algoritmos (EXECUTION_MODE del backend), dicho para
// quien no sabe que es SLURM.
const MODO_EJECUCION = {
  local: 'en este mismo servidor',
  slurm: 'en el clúster de cálculo de la UAL',
}

const Panel = ({ titulo, icono, children }) => (
  <section className="panel panel-sistema">
    <h3><Icono nombre={icono} />{titulo}</h3>
    <dl className="metricas">{children}</dl>
  </section>
)

// `estado` colorea la cifra con los tokens de estado (completado, error...),
// los mismos de las insignias de Resultados.
const Metrica = ({ label, valor, estado }) => (
  <div className="metrica">
    <dt>{label}</dt>
    <dd className={estado ? `cifra-${estado}` : ''}>{valor}</dd>
  </div>
)

export default function Sistema() {
  const [estado, setEstado] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    const cargar = async () => {
      try {
        const resp = await apiFetch('/sistema/estado')
        if (resp.status === 403) {
          setError('Tu cuenta no tiene permiso para ver esta página.')
          return
        }
        if (!resp.ok) throw await errorDeRespuesta(resp)
        setEstado(await resp.json())
        setError(null)
      } catch (err) {
        setError(mensajeError('consultar el estado de la plataforma', err))
      }
    }
    cargar()
    const intervalo = setInterval(cargar, POLL_MS)
    return () => clearInterval(intervalo)
  }, [])

  if (error && !estado) {
    return <div className="seccion-wrapper"><h2>Estado del sistema</h2><p className="error-msg" role="status">{error}</p></div>
  }
  if (!estado) {
    return <div className="seccion-wrapper"><h2>Estado del sistema</h2><p className="texto-secundario">Cargando…</p></div>
  }

  const { servidor, cola, peticiones, workflows, usuarios } = estado
  const hayProcesos = cola.disponible && cola.workers_conectados > 0

  return (
    <div className="seccion-wrapper">
      <h2>Estado del sistema</h2>
      <p className="seccion-subtitulo">
        Los algoritmos se ejecutan {MODO_EJECUCION[servidor.modo_ejecucion] || servidor.modo_ejecucion}.
        Datos del {formatFecha(servidor.hora_utc)}; se actualizan solos cada {POLL_MS / 1000} segundos.
      </p>

      {/* Si una consulta falla despues de la primera, se avisa pero se dejan
          los ultimos datos: mejor eso que una pagina en blanco. */}
      {error && <p className="error-msg" role="status">{error} Se muestran los últimos datos recibidos.</p>}

      {/* Lo primero que hay que saber: si los trabajos se estan atendiendo. */}
      <p className={`estado-cola ${hayProcesos ? 'exito-msg' : 'error-msg'}`} role="status">
        <Icono nombre={hayProcesos ? 'ok' : 'aviso'} />
        {!cola.disponible
          ? 'No se puede consultar la cola de trabajos. Los trabajos nuevos esperarán hasta que vuelva a funcionar.'
          : hayProcesos
            ? 'La plataforma está atendiendo trabajos con normalidad.'
            : 'No hay ningún proceso de cálculo en marcha: los trabajos se quedarán en cola hasta que arranque alguno.'}
      </p>

      <div className="paneles-sistema">
        <Panel titulo="Procesos de cálculo" icono="procesando">
          {cola.disponible ? (
            <>
              <Metrica label="Procesos conectados" valor={cola.workers_conectados}
                       estado={cola.workers_conectados > 0 ? 'completado' : 'error'} />
              <Metrica label="Trabajos en marcha ahora" valor={cola.tareas_en_ejecucion} estado="procesando" />
              <Metrica label="Trabajos a la vez por proceso" valor={cola.worker_concurrency_configurado} />
            </>
          ) : (
            <Metrica label="Estado" valor="Sin datos" estado="error" />
          )}
        </Panel>

        <Panel titulo="Peticiones" icono="matraz">
          <Metrica label="Total" valor={peticiones.total} />
          <Metrica label="En cola" valor={peticiones.pendientes} estado="pendiente" />
          <Metrica label="Procesando" valor={peticiones.procesando} estado="procesando" />
          <Metrica label="Completadas" valor={peticiones.completadas} estado="completado" />
          <Metrica label="Con error" valor={peticiones.error} estado="error" />
        </Panel>

        <Panel titulo="Workflows" icono="grafico">
          <Metrica label="Workflows creados" valor={workflows.total} />
          <Metrica label="Ejecuciones en total" valor={workflows.ejecuciones_total} />
          <Metrica label="En marcha" valor={workflows.ejecuciones_activas} estado="procesando" />
          <Metrica label="Completadas" valor={workflows.ejecuciones_completadas} estado="completado" />
          <Metrica label="Con error" valor={workflows.ejecuciones_error} estado="error" />
        </Panel>

        <Panel titulo="Usuarios" icono="ok">
          <Metrica label="Registrados" valor={usuarios.total} />
          <Metrica label="Con el correo verificado" valor={usuarios.verificados} estado="completado" />
        </Panel>
      </div>
    </div>
  )
}
