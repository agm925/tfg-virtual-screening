import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../../api/client'
import { crearContadorDeBusquedas } from '../../utils/visor'
import { errorDeRespuesta, mensajeError } from '../../utils/mensajes'
import Icono from '../Icono'

const BLOQUE = 50
// Si el primer bloque tarda más que esto, es que el servidor está
// construyendo el mapa de la biblioteca (primera apertura, RNF-1): se avisa.
const AVISO_PREPARANDO_MS = 1000

// La lista de moléculas de un SDF (RF-6): por nombre o posición, de 50 en 50
// al desplazarse, sin traer nunca el fichero entero.
export default function ListaMoleculas({ fichero, alElegir }) {
  const [consulta, setConsulta] = useState('')
  const [moleculas, setMoleculas] = useState([])
  const [pagina, setPagina] = useState(null)        // { total, hay_mas, fuera_de_rango } de la última respuesta
  const [cargando, setCargando] = useState(false)
  const [preparando, setPreparando] = useState(false)
  const [error, setError] = useState(null)           // { texto, offset } del bloque que falló
  const contador = useRef(crearContadorDeBusquedas())
  const busquedaActual = useRef(0)

  // Pide un bloque. `offset` 0 empieza la lista de nuevo (búsqueda nueva);
  // cualquier otro la continúa. Una respuesta de una búsqueda que ya no es la
  // vigente se descarta (RF-6).
  const cargar = async (offset, idBusqueda) => {
    setCargando(true)
    setError(null)
    const avisoLento = offset === 0 ? setTimeout(() => setPreparando(true), AVISO_PREPARANDO_MS) : null
    try {
      const params = new URLSearchParams({ q: consulta, offset, limit: BLOQUE })
      const resp = await apiFetch(`/visor/ficheros/${encodeURIComponent(fichero)}/moleculas?${params}`)
      if (!resp.ok) throw await errorDeRespuesta(resp)
      const datos = await resp.json()
      if (!contador.current.esVigente(idBusqueda)) return
      setMoleculas(m => (offset === 0 ? datos.coincidencias : [...m, ...datos.coincidencias]))
      setPagina(datos)
      // Una biblioteca de un solo registro se trata como una molécula suelta (RF-5).
      if (offset === 0 && !consulta && datos.total === 1) alElegir(1)
    } catch (err) {
      if (!contador.current.esVigente(idBusqueda)) return
      // Lo ya cargado se conserva; solo se reintenta el bloque que falló.
      setError({ texto: mensajeError('cargar la lista de moléculas', err), offset })
    } finally {
      clearTimeout(avisoLento)
      if (contador.current.esVigente(idBusqueda)) {
        setCargando(false)
        setPreparando(false)
      }
    }
  }

  useEffect(() => {
    const id = contador.current.siguiente()
    busquedaActual.current = id
    const espera = setTimeout(() => cargar(0, id), consulta ? 250 : 0)
    return () => clearTimeout(espera)
    // `cargar` se rehace en cada render; lo que dispara la búsqueda es esto.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [consulta, fichero])

  const cargarMas = () => {
    if (!cargando && pagina?.hay_mas) cargar(moleculas.length, busquedaActual.current)
  }

  // Al acercarse al final de la lista, el bloque siguiente.
  const alDesplazar = (e) => {
    const { scrollTop, clientHeight, scrollHeight } = e.currentTarget
    if (scrollTop + clientHeight >= scrollHeight - 60) cargarMas()
  }

  return (
    <section className="visor3d-moleculas" aria-label={`Moléculas de ${fichero}`}>
      <h4>Moléculas de {fichero}</h4>
      <label htmlFor="visor-buscar-molecula" className="visor3d-etiqueta">Nombre o número</label>
      <input
        id="visor-buscar-molecula"
        type="search"
        className="visor3d-campo"
        placeholder="Por ejemplo, CHEMBL25 o 25"
        value={consulta}
        onChange={e => setConsulta(e.target.value)}
      />

      {preparando && (
        <p className="texto-secundario" role="status">
          Preparando la biblioteca… La primera vez que se abre tarda un poco más.
        </p>
      )}
      {pagina?.fuera_de_rango && (
        <p className="texto-secundario" role="status">
          No hay ninguna molécula en esa posición: esta biblioteca tiene {pagina.total}.
        </p>
      )}
      {pagina && moleculas.length === 0 && !pagina.fuera_de_rango && (
        <p className="texto-secundario" role="status">Ninguna molécula coincide con «{consulta}».</p>
      )}

      <ul className="visor3d-lista" onScroll={alDesplazar}>
        {moleculas.map(m => (
          <li key={m.posicion}>
            <button className="visor3d-item" onClick={() => alElegir(m.posicion)}>
              <span className="visor3d-item-nombre">{m.nombre}</span>
              <span className="visor3d-item-detalle">nº {m.posicion}</span>
            </button>
          </li>
        ))}
      </ul>

      {error && (
        <div className="error-msg" role="status">
          {error.texto}{' '}
          <button className="btn-enlace"
                  onClick={() => cargar(error.offset, busquedaActual.current)}>Reintentar</button>
        </div>
      )}
      {cargando && !preparando && <p className="texto-secundario">Cargando…</p>}
      {pagina?.hay_mas && !cargando && !error && (
        <button className="btn-secundario visor3d-mas" onClick={cargarMas}>
          <Icono nombre="bajar" />Cargar más
        </button>
      )}
    </section>
  )
}
