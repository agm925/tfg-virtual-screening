import { useRef } from 'react'
import Icono from './Icono'
import { useIdioma } from '../hooks/useIdioma'

// Elegir un fichero con un botón propio (spec 014). El selector del navegador
// escribe «Seleccionar archivo» y «Ningún archivo seleccionado» en el idioma
// del sistema, no en el de la página, y no se puede cambiar: con la interfaz
// en inglés salía en español. Aquí queda oculto y lo abre el botón.
//
// `id` es el del botón, para que el <label htmlFor> de quien lo usa lo
// nombre. Se vacía el input tras cada elección: si no, volver a elegir el
// mismo fichero (después de subirlo o de un error) no avisaría de nada.
export default function SelectorFichero({ id, accept, fichero, alElegir, className = '' }) {
  const { t } = useIdioma()
  const entrada = useRef()

  return (
    <div className={`selector-fichero ${className}`}>
      <input
        ref={entrada}
        type="file"
        accept={accept}
        hidden
        onChange={e => {
          const elegido = e.target.files[0]
          e.target.value = ''
          if (elegido) alElegir(elegido)
        }}
      />
      <button id={id} type="button" className="btn-secundario" onClick={() => entrada.current?.click()}
              aria-describedby={`${id}-nombre`}>
        <Icono nombre="fichero" />{t('fichero.elegir')}
      </button>
      <span id={`${id}-nombre`} className="selector-fichero-nombre" title={fichero?.name}>
        {fichero ? fichero.name : t('fichero.ninguno')}
      </span>
    </div>
  )
}
