import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../../api/client'
import { crearContadorDeBusquedas } from '../../utils/visor'
import { errorDeRespuesta, mensajeError } from '../../utils/mensajes'
import Icono from '../Icono'

const GRUPOS = [
  { id: 'molecula', titulo: 'Moléculas' },
  { id: 'biblioteca', titulo: 'Bibliotecas' },
  { id: 'resultado', titulo: 'Resultados' },
]

function detalle(f) {
  if (f.formato === 'sdf' && f.grupo !== 'molecula' && f.num_moleculas === null) return 'Contando moléculas…'
  if (f.num_moleculas > 1) return `${f.num_moleculas} moléculas`
  return f.formato.toUpperCase()
}

// Buscador de ficheros del visor (RF-3): todos los que el usuario puede ver,
// agrupados y con lo más reciente primero (el orden lo da el servidor), y
// filtrados por nombre al escribir.
export default function BuscadorFicheros({ abierto, alElegir, irA }) {
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
        setError(mensajeError('cargar la lista de ficheros', err))
      }
    }, consulta ? 250 : 0)
    return () => clearTimeout(espera)
  }, [consulta, reintentos])

  return (
    <>
      <label htmlFor="visor-buscar-fichero" className="visor3d-etiqueta">Buscar fichero</label>
      <input
        id="visor-buscar-fichero"
        type="search"
        className="visor3d-campo"
        placeholder="Nombre de la molécula, biblioteca o resultado"
        value={consulta}
        onChange={e => setConsulta(e.target.value)}
      />

      {error && (
        <div className="error-msg" role="status">
          {error}{' '}
          <button className="btn-enlace" onClick={() => setReintentos(n => n + 1)}>Reintentar</button>
        </div>
      )}

      {ficheros === null && !error && <p className="texto-secundario">Cargando…</p>}

      {ficheros?.length === 0 && (consulta ? (
        <p className="texto-secundario" role="status">Ningún fichero coincide con «{consulta}».</p>
      ) : (
        <div className="visor3d-vacio" role="status">
          <p>Todavía no hay ficheros que puedas ver. Sube una molécula o una biblioteca para empezar.</p>
          <button className="btn-primary" onClick={() => irA('moleculas')}>
            <Icono nombre="subir" />Ir a Moléculas
          </button>
        </div>
      ))}

      {ficheros?.length > 0 && GRUPOS.map(({ id, titulo }) => {
        const delGrupo = ficheros.filter(f => f.grupo === id)
        if (delGrupo.length === 0) return null
        return (
          <section key={id} className="visor3d-grupo" aria-label={titulo}>
            <h4>{titulo}</h4>
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
                    <span className="visor3d-item-detalle">{detalle(f)}</span>
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
