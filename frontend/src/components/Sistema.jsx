import { useState, useEffect } from 'react'
import { apiFetch } from '../api/client'
import Icono from './Icono'
import { formatFecha } from '../utils/ficheros'
import { errorDeRespuesta, mensajeError } from '../utils/mensajes'
import { avisoCopias, tamanoLegible } from '../utils/sistema'
import { useIdioma } from '../hooks/useIdioma'
import '../styles/Sistema.css'

const POLL_MS = 8000

// Donde se ejecutan los algoritmos (EXECUTION_MODE del backend), dicho para
// quien no sabe que es SLURM: la clave de su texto.
const MODO_EJECUCION = {
  local: 'sistema.modo_local',
  slurm: 'sistema.modo_slurm',
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
  const { t, idioma } = useIdioma()
  const [estado, setEstado] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    const cargar = async () => {
      try {
        const resp = await apiFetch('/sistema/estado')
        if (resp.status === 403) {
          setError(t('admin.sin_permiso'))
          return
        }
        if (!resp.ok) throw await errorDeRespuesta(resp)
        setEstado(await resp.json())
        setError(null)
      } catch (err) {
        setError(mensajeError(t('accion.consultar_estado'), err, t))
      }
    }
    cargar()
    const intervalo = setInterval(cargar, POLL_MS)
    return () => clearInterval(intervalo)
    // Al cambiar de idioma no se reinicia el sondeo: el próximo error ya sale traducido.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (error && !estado) {
    return <div className="seccion-wrapper"><h2>{t('sistema.titulo')}</h2><p className="error-msg" role="status">{error}</p></div>
  }
  if (!estado) {
    return <div className="seccion-wrapper"><h2>{t('sistema.titulo')}</h2><p className="texto-secundario">{t('comun.cargando')}</p></div>
  }

  const { servidor, cola, peticiones, workflows, usuarios, copias } = estado
  const hayProcesos = cola.disponible && cola.workers_conectados > 0
  const aviso = avisoCopias(copias, t)

  return (
    <div className="seccion-wrapper">
      <h2>{t('sistema.titulo')}</h2>
      <p className="seccion-subtitulo">
        {t('sistema.subtitulo', {
          modo: MODO_EJECUCION[servidor.modo_ejecucion] ? t(MODO_EJECUCION[servidor.modo_ejecucion]) : servidor.modo_ejecucion,
          fecha: formatFecha(servidor.hora_utc, idioma),
          segundos: POLL_MS / 1000,
        })}
      </p>

      {/* Si una consulta falla despues de la primera, se avisa pero se dejan
          los ultimos datos: mejor eso que una pagina en blanco. */}
      {error && <p className="error-msg" role="status">{error} {t('sistema.ultimos_datos')}</p>}

      {/* Lo primero que hay que saber: si los trabajos se estan atendiendo. */}
      <p className={`estado-cola ${hayProcesos ? 'exito-msg' : 'error-msg'}`} role="status">
        <Icono nombre={hayProcesos ? 'ok' : 'aviso'} />
        {!cola.disponible
          ? t('sistema.cola_no_disponible')
          : hayProcesos
            ? t('sistema.cola_ok')
            : t('sistema.sin_procesos')}
      </p>

      {/* Spec 009: si nadie mira las copias, nadie se entera de que han
          dejado de hacerse. */}
      {aviso && (
        <p className="estado-cola error-msg" role="status"><Icono nombre="aviso" />{aviso}</p>
      )}

      <div className="paneles-sistema">
        <Panel titulo={t('sistema.procesos')} icono="procesando">
          {cola.disponible ? (
            <>
              <Metrica label={t('sistema.procesos_conectados')} valor={cola.workers_conectados}
                       estado={cola.workers_conectados > 0 ? 'completado' : 'error'} />
              <Metrica label={t('sistema.trabajos_ahora')} valor={cola.tareas_en_ejecucion} estado="procesando" />
              <Metrica label={t('sistema.trabajos_por_proceso')} valor={cola.worker_concurrency_configurado} />
            </>
          ) : (
            <Metrica label={t('tabla.estado')} valor={t('sistema.sin_datos')} estado="error" />
          )}
        </Panel>

        <Panel titulo={t('sistema.peticiones')} icono="matraz">
          <Metrica label={t('sistema.total')} valor={peticiones.total} />
          <Metrica label={t('estado.pendiente')} valor={peticiones.pendientes} estado="pendiente" />
          <Metrica label={t('estado.procesando')} valor={peticiones.procesando} estado="procesando" />
          <Metrica label={t('sistema.completadas')} valor={peticiones.completadas} estado="completado" />
          <Metrica label={t('sistema.con_error')} valor={peticiones.error} estado="error" />
        </Panel>

        <Panel titulo={t('sistema.workflows')} icono="grafico">
          <Metrica label={t('sistema.workflows_creados')} valor={workflows.total} />
          <Metrica label={t('sistema.ejecuciones_total')} valor={workflows.ejecuciones_total} />
          <Metrica label={t('sistema.en_marcha')} valor={workflows.ejecuciones_activas} estado="procesando" />
          <Metrica label={t('sistema.completadas')} valor={workflows.ejecuciones_completadas} estado="completado" />
          <Metrica label={t('sistema.con_error')} valor={workflows.ejecuciones_error} estado="error" />
        </Panel>

        <Panel titulo={t('admin.usuarios')} icono="ok">
          <Metrica label={t('sistema.registrados')} valor={usuarios.total} />
          <Metrica label={t('sistema.verificados')} valor={usuarios.verificados} estado="completado" />
        </Panel>

        <Panel titulo={t('sistema.copias')} icono="guardar">
          <Metrica label={t('sistema.ultima_copia')} valor={copias?.ultima ? formatFecha(copias.ultima.fecha, idioma) : t('sistema.ninguna')}
                   estado={aviso ? 'error' : 'completado'} />
          {copias?.ultima && (
            <>
              <Metrica label={t('tabla.ficheros')} valor={copias.ultima.ficheros} />
              <Metrica label={t('tabla.tamano')} valor={tamanoLegible(copias.ultima.bytes, idioma)} />
            </>
          )}
        </Panel>
      </div>
    </div>
  )
}
