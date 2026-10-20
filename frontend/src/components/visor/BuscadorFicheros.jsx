import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../../api/client'
import { crearContadorDeBusquedas, detalleFichero } from '../../utils/visor'
import { errorDeRespuesta, mensajeError } from '../../utils/mensajes'
import Icono from '../Icono'
import { useIdioma } from '../../hooks/useIdioma'

const GRUPOS = [
  { id: 'molecula', titulo: 'tabla.moleculas' },
  { id: 'biblioteca', titulo: 'moleculas.bibliotecas' },
  { id: 'resultado', titulo: 'cabecera.resultados' },
]

// Buscador de ficheros del visor (RF-3): todos los que el usuario puede ver,
// agrupados y con lo más reciente primero (el orden lo da el servidor), y
// filtrados por nombre al escribir.
export default function BuscadorFicheros({ abierto, alElegir, irA }) {
  const { t } = useIdioma()
  const [consulta, setConsulta] = useState('')
  const [ficheros, setFicheros] = useState(null)   // null = cargando
  const [error, setError] = useState(null)
  const [reintentos, setReintentos] = useState(0)
  const contador = useRef(crearContadorDeBusquedas())

  useEffect(() => {
    const id = contador.current.siguiente()
    // Se espera a que el usuario deje de teclear; y si mientras tanto ha
    // escrito otra cosa, esta respuesta ya no se pinta (RF-6).
    const espera = setTimeout(async () => {
      try {
        const resp = await apiFetch(`/visor/ficheros?q=${encodeURIComponent(consulta)}`)
        if (!resp.ok) throw await errorDeRespuesta(resp)
        const datos = await resp.json()
        if (!contador.current.esVigente(id)) return
        setFicheros(datos)
        setError(null)
      } catch (err) {
        if (!contador.current.esVigente(id)) return
        setError(mensajeError(t('accion.cargar_ficheros'), err, t))
      }
    }, consulta ? 250 : 0)
    return () => clearTimeout(espera)
    // `t` no dispara una búsqueda: cambia el texto del error, no lo que se pide.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [consulta, reintentos])

  return (
    <>
      <label htmlFor="visor-buscar-fichero" className="visor3d-etiqueta">{t('visor.buscar_fichero')}</label>
      <input
        id="visor-buscar-fichero"
        type="search"
        className="visor3d-campo"
        placeholder={t('visor.buscar_fichero_ejemplo')}
        value={consulta}
        onChange={e => setConsulta(e.target.value)}
      />

      {error && (
        <div className="error-msg" role="status">
          {error}{' '}
          <button className="btn-enlace" onClick={() => setReintentos(n => n + 1)}>{t('comun.reintentar')}</button>
        </div>
      )}

      {ficheros === null && !error && <p className="texto-secundario">{t('comun.cargando')}</p>}

      {ficheros?.length === 0 && (consulta ? (
        <p className="texto-secundario" role="status">{t('visor.ningun_fichero', { consulta })}</p>
      ) : (
        <div className="visor3d-vacio" role="status">
          <p>{t('visor.sin_ficheros')}</p>
          <button className="btn-primary" onClick={() => irA('moleculas')}>
            <Icono nombre="subir" />{t('visor.ir_moleculas')}
          </button>
        </div>
      ))}

      {ficheros?.length > 0 && GRUPOS.map(({ id, titulo }) => {
        const delGrupo = ficheros.filter(f => f.grupo === id)
        if (delGrupo.length === 0) return null
        return (
          <section key={id} className="visor3d-grupo" aria-label={t(titulo)}>
            <h4>{t(titulo)}</h4>
            <ul className="visor3d-lista">
              {delGrupo.map(f => (
                <li key={f.nombre}>
                  <button
                    className={`visor3d-item ${abierto === f.nombre ? 'abierto' : ''}`}
                    aria-pressed={abierto === f.nombre}
                    onClick={() => alElegir(f)}
                    title={f.nombre}
                  >
                    <span className="visor3d-item-nombre">{f.nombre}</span>
                    <span className="visor3d-item-detalle">{detalleFichero(f, t)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </>
  )
}
