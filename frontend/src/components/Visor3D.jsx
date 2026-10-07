import { useEffect, useRef, useState } from 'react'
import { apiFetch, descargarConToken } from '../api/client'
import {
  HUECOS, colocar, activar, vaciar, tieneLista, modoDisponible,
  claveVisor, serializar, restaurar, ponerEnHueco,
  abrirDesdeFuera, llegaConLista,
} from '../utils/visor'
import { errorDeRespuesta, mensajeError } from '../utils/mensajes'
import BuscadorFicheros from './visor/BuscadorFicheros'
import ListaMoleculas from './visor/ListaMoleculas'
import Hueco from './visor/Hueco'
import LienzoVisor from './visor/LienzoVisor'
import '../styles/Visor3D.css'

// Página Visor 3D (spec 002, docs/specs/002-visor3D/). Busca cualquier
// fichero que el usuario puede ver, coloca hasta dos moléculas en los huecos
// A y B y las dibuja juntas o lado a lado.
//
// El estado de la pantalla (qué hay en cada hueco, cuál está activo, modo y
// estilos) lo llevan las funciones puras de utils/visor.js, probadas con
// node --test; aquí solo se pinta y se llama a la API (principio 3).
const ruta = (fichero, accion, posicion) =>
  `/visor/ficheros/${encodeURIComponent(fichero)}/${accion}${posicion === null ? '' : `?posicion=${posicion}`}`

// La molécula que el servidor tiene para (fichero, posición), ya analizada.
// null si ya no está disponible: el servidor responde 404 tanto si se ha
// borrado como si se ha dejado de tener acceso (RF-13).
async function pedirMolecula(fichero, posicion) {
  const resp = await apiFetch(ruta(fichero, 'molecula', posicion))
  if (resp.status === 404) return null
  if (!resp.ok) throw await errorDeRespuesta(resp)
  return { ...(await resp.json()), fichero, posicion }
}

// Lo guardado en la pestaña (RF-14); sin acceso a sessionStorage (modo
// privado, cuota), se empieza de cero.
function leerGuardado(clave) {
  try {
    return restaurar(sessionStorage.getItem(clave))
  } catch {
    return restaurar(null)
  }
}

// `llegada`: el fichero de un «Ver en 3D» de otra página (RF-15), o null si
// se entra desde el menú. Se lee solo al montar, y `alLlegar` avisa a App.jsx
// de que ya está consumido.
export default function Visor3D({ usuario, irA, llegada, alLlegar }) {
  const clave = claveVisor(usuario.id)
  const [llegadaInicial] = useState(llegada)
  const conLista = Boolean(llegadaInicial) && llegaConLista(llegadaInicial)
  // Lo guardado se lee una vez: los huecos traen solo qué molécula era
  // (fichero y posición) y se vuelven a pedir al servidor al montar. Un SDF
  // que llega desde fuera deja A activo, para que lo que se elija de su lista
  // vaya a A; lo que había en A sigue a la vista hasta entonces.
  const [guardado] = useState(() => {
    const leido = leerGuardado(clave)
    return conLista ? activar(leido, 'A') : leido
  })
  const [estado, setEstado] = useState(() => ({ ...guardado, huecos: { A: null, B: null } }))
  const [restaurando, setRestaurando] = useState(() => HUECOS.some(h => guardado.huecos[h] !== null))
  // SDF cuya lista se está viendo; uno que llega desde fuera, ya desplegado.
  const [abierto, setAbierto] = useState(conLista ? llegadaInicial : null)
  const [aviso, setAviso] = useState(null)       // { texto, reintentar? }

  // Un fichero que estaba en un hueco ya no está: se quita y se dice por qué.
  const quitarPerdido = (h, nombre) => {
    setEstado(e => vaciar(e, h))
    setAviso({ texto: `«${nombre}» ya no está disponible (se ha borrado o ya no tienes acceso), `
      + `así que se ha quitado del hueco ${h}.` })
  }

  // Pide la molécula y la pone en el hueco activo, o en A si llega desde
  // fuera (`ponerCon` = abrirDesdeFuera). `posicion` null: el fichero entero.
  const colocarMolecula = async (fichero, posicion = null, ponerCon = colocar) => {
    setAviso(null)
    try {
      const molecula = await pedirMolecula(fichero, posicion)
      if (molecula === null) {
        setAviso({ texto: `«${fichero}» ya no está disponible: se ha borrado o ya no tienes acceso.` })
        return
      }
      setEstado(e => ponerCon(e, molecula))
    } catch (err) {
      setAviso({
        texto: mensajeError('abrir la molécula', err),
        reintentar: () => colocarMolecula(fichero, posicion, ponerCon),
      })
    }
  }

  // Lo que llega desde «Ver en 3D» (RF-15). Un SDF ya tiene su lista
  // desplegada y A activo; el resto se coloca en A conservando B, pero solo
  // cuando B ya se ha recuperado: si llegara antes, el activo pasaría a B
  // (RF-4) aunque B acabe ocupado.
  const llegadaPendiente = useRef(Boolean(llegadaInicial) && !conLista)
  useEffect(() => {
    if (llegadaInicial) alLlegar()
    // Solo al montar: App.jsx olvida el fichero, que ya está leído.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => {
    if (restaurando || !llegadaPendiente.current) return
    llegadaPendiente.current = false
    colocarMolecula(llegadaInicial, null, abrirDesdeFuera)
    // Se dispara al terminar la restauración; lo demás no cambia.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restaurando])

  // El nombre del fichero lo pone el servidor (visor.nombre_descarga).
  const descargar = async (h) => {
    const { fichero, posicion, nombre } = estado.huecos[h]
    setAviso(null)
    try {
      await descargarConToken(ruta(fichero, 'descarga', posicion))
    } catch (err) {
      if (err.status === 404) quitarPerdido(h, nombre)
      else setAviso({ texto: mensajeError('descargar la molécula', err), reintentar: () => descargar(h) })
    }
  }

  // Al volver a la página: cada molécula guardada se pide de nuevo al
  // servidor, que comprueba que sigue existiendo y que se puede ver (RF-13).
  useEffect(() => {
    if (!restaurando) return
    let vigente = true
    Promise.all(HUECOS.map(async (h) => {
      const ref = guardado.huecos[h]
      if (ref === null) return
      try {
        const molecula = await pedirMolecula(ref.fichero, ref.posicion)
        if (!vigente) return
        if (molecula === null) quitarPerdido(h, ref.fichero)
        else setEstado(e => ponerEnHueco(e, h, molecula))
      } catch (err) {
        if (vigente) setAviso({ texto: mensajeError('recuperar las moléculas de antes', err) })
      }
    })).then(() => { if (vigente) setRestaurando(false) })
    return () => { vigente = false }
    // Solo al montar: `guardado` no cambia después.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Se guarda en cada cambio; mientras se restaura no, para no pisar lo
  // guardado con los huecos aún vacíos.
  useEffect(() => {
    if (restaurando) return
    try {
      sessionStorage.setItem(clave, serializar(estado))
    } catch { /* sin almacenamiento: no se recupera al volver, nada más */ }
  }, [estado, restaurando, clave])

  const elegirFichero = (f) => {
    if (tieneLista(f)) {
      setAbierto(f.nombre)
    } else {
      setAbierto(null)
      colocarMolecula(f.nombre)
    }
  }

  return (
    <div className="seccion-wrapper visor3d">
      <h2>Visor 3D</h2>
      <p className="seccion-subtitulo">
        Busca una molécula, una biblioteca o un resultado y colócalo en el hueco A o B para
        verlo en 3D. Con dos moléculas puedes verlas juntas o lado a lado.
      </p>

      {restaurando && <p className="texto-secundario" role="status">Recuperando las moléculas de antes…</p>}
      {aviso && (
        <p className="error-msg" role="status">
          {aviso.texto}
          {aviso.reintentar && <> <button className="btn-enlace" onClick={aviso.reintentar}>Reintentar</button></>}
        </p>
      )}

      <div className="visor3d-rejilla">
        <aside className="panel visor3d-buscador" aria-label="Elegir molécula">
          <BuscadorFicheros abierto={abierto} alElegir={elegirFichero} irA={irA} />
          {abierto && (
            <ListaMoleculas key={abierto} fichero={abierto}
                            alElegir={posicion => colocarMolecula(abierto, posicion)} />
          )}
        </aside>

        <div className="visor3d-principal">
          {modoDisponible(estado) && (
            <div className="visor3d-modo" role="group" aria-label="Cómo ver las dos moléculas">
              {[['superpuestas', 'Superpuestas'], ['lado_a_lado', 'Lado a lado']].map(([modo, texto]) => (
                <button key={modo} className="visor3d-modo-opcion" aria-pressed={estado.modo === modo}
                        onClick={() => setEstado(e => ({ ...e, modo }))}>
                  {texto}
                </button>
              ))}
            </div>
          )}

          <section className={`visor3d-lienzo ${estado.modo === 'lado_a_lado' && modoDisponible(estado) ? 'lado-a-lado' : ''}`}
                   aria-label="Dibujo 3D">
            <LienzoVisor estado={estado} />
          </section>

          <div className="visor3d-huecos">
            {HUECOS.map(h => (
              <Hueco
                key={h}
                hueco={h}
                molecula={estado.huecos[h]}
                estilo={estado.estilos[h]}
                activo={estado.activo === h}
                alCambiarEstilo={estilo => setEstado(e => ({ ...e, estilos: { ...e.estilos, [h]: estilo } }))}
                alActivar={() => setEstado(e => activar(e, h))}
                alVaciar={() => setEstado(e => vaciar(e, h))}
                alDescargar={() => descargar(h)}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
