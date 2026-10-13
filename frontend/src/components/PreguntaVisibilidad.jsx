import { useEffect, useRef } from 'react'
import Icono from './Icono'
import '../styles/PreguntaVisibilidad.css'

// Pregunta, antes de cada subida, quién podrá ver el fichero (spec 007). Se
// usa <dialog> con showModal y no un div propio: el navegador ya lo hace
// modal, cierra con Escape y no deja que el foco se escape a la página.
// Ninguna opción viene marcada: elegir es justo lo que se pide.
export default function PreguntaVisibilidad({ fichero, alElegir, alCancelar }) {
  const ref = useRef()
  const cancelar = useRef()
  const abierto = Boolean(fichero)

  useEffect(() => {
    const dialogo = ref.current
    if (!dialogo) return
    if (abierto && !dialogo.open) {
      dialogo.showModal()
      // El foco empieza en Cancelar: en «Privado», el primer botón, parecía
      // la opción ya elegida, y un Enter despistado no debe subir nada. Va
      // aquí y no con autoFocus porque React no lo escribe en el HTML y
      // showModal no lo vería.
      cancelar.current.focus()
    }
    if (!abierto && dialogo.open) dialogo.close()
  }, [abierto])

  return (
    <dialog
      ref={ref}
      className="pregunta-visibilidad"
      aria-labelledby="pregunta-visibilidad-titulo"
      // Escape: el navegador lo cierra; se avisa para que no quede abierto
      // en el estado de quien lo usa.
      onCancel={e => { e.preventDefault(); alCancelar() }}
    >
      <h3 id="pregunta-visibilidad-titulo">¿Quién puede ver este fichero?</h3>
      {fichero && <p className="texto-secundario pregunta-visibilidad-fichero">{fichero}</p>}

      <div className="pregunta-visibilidad-opciones">
        <button type="button" className="opcion-visibilidad" onClick={() => alElegir(false)}>
          <Icono nombre="candado" tamano={24} />
          <span className="opcion-visibilidad-titulo">Privado</span>
          <span className="opcion-visibilidad-texto">Solo tú.</span>
        </button>
        <button type="button" className="opcion-visibilidad" onClick={() => alElegir(true)}>
          <Icono nombre="personas" tamano={24} />
          <span className="opcion-visibilidad-titulo">Público</span>
          <span className="opcion-visibilidad-texto">Todos los usuarios, en Moléculas.</span>
        </button>
      </div>

      <p className="texto-secundario">No se puede cambiar después de subirlo.</p>
      <button ref={cancelar} type="button" className="btn-secundario" onClick={alCancelar}>Cancelar</button>
    </dialog>
  )
}
