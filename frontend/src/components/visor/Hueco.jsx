import { useState } from 'react'
import { recortar, ESTILOS, estiloEfectivo } from '../../utils/visor'
import Icono from '../Icono'

// Un campo del registro (RF-10). El valor lo escribió quien subió el fichero:
// va siempre como texto de React, nunca como HTML (RNF-2). Si es largo se
// enseña el principio y se puede ver entero.
function Campo({ nombre, valor }) {
  const [entero, setEntero] = useState(false)
  const { corto, completo, recortado } = recortar(valor)
  return (
    <>
      <dt>{nombre}</dt>
      <dd>
        <span className="visor3d-valor">{entero ? completo : corto}{recortado && !entero && '…'}</span>
        {recortado && (
          <button className="btn-enlace visor3d-ver-completo" onClick={() => setEntero(!entero)}>
            {entero ? 'ver menos' : 'ver completo'}
          </button>
        )}
      </dd>
    </>
  )
}

// Cómo se dibuja la molécula del hueco (RF-9). Si se piden cintas para algo
// que el fichero no declara como proteína, se dice por qué se ve en varillas.
function SelectorEstilo({ hueco, molecula, estilo, alCambiar }) {
  const { estilo: efectivo, aviso } = estiloEfectivo(estilo, molecula)
  const id = `visor-estilo-${hueco}`
  return (
    <div className="visor3d-estilo">
      <label htmlFor={id} className="visor3d-etiqueta">Representación</label>
      <select id={id} className="visor3d-campo" value={estilo ?? efectivo}
              onChange={e => alCambiar(e.target.value)}>
        {ESTILOS.map(e => <option key={e.valor} value={e.valor}>{e.etiqueta}</option>)}
      </select>
      {aviso && <p className="visor3d-aviso" role="status">{aviso}</p>}
    </div>
  )
}

// Avisos sobre cómo se ve la molécula (RF-12), en lenguaje llano.
const AVISO_2D = 'Esta molécula solo tiene coordenadas en 2D, así que se ve plana.'
const AVISO_SIN_ENLACES = 'Este formato no trae los enlaces: los que ves los deduce el visor por la distancia '
  + 'entre átomos y pueden no ser exactos.'

// El panel de un hueco (A o B, RF-4): su color, si es el activo, qué
// molécula tiene y sus datos (RF-10), y la descarga (RF-11).
export default function Hueco({ hueco, molecula, estilo, activo, alActivar, alVaciar, alDescargar, alCambiarEstilo }) {
  return (
    <section className={`panel visor3d-hueco hueco-${hueco.toLowerCase()} ${activo ? 'activo' : ''}`}
             aria-label={`Molécula ${hueco}`}>
      <div className="visor3d-hueco-cabecera">
        <h3><span className="visor3d-muestra" aria-hidden="true" />Molécula {hueco}</h3>
        {activo ? (
          <span className="visor3d-activo">Hueco activo</span>
        ) : (
          <button className="btn-enlace" onClick={alActivar}>Usar este hueco</button>
        )}
      </div>

      {!molecula && (
        <p className="texto-secundario">
          Vacío.{activo && ' Lo próximo que elijas en la lista irá aquí.'}
        </p>
      )}

      {molecula && (
        <>
          <p className="visor3d-hueco-nombre">{molecula.nombre}</p>
          {/* El motivo lo da el servidor; la molécula del otro hueco se sigue viendo. */}
          {!molecula.dibujable && <p className="visor3d-no-dibujable" role="status">{molecula.motivo}</p>}
          {molecula.dibujable && (
            <SelectorEstilo hueco={hueco} molecula={molecula} estilo={estilo} alCambiar={alCambiarEstilo} />
          )}
          {molecula.dibujable && molecula.solo_2d && <p className="visor3d-aviso">{AVISO_2D}</p>}
          {molecula.dibujable && molecula.sin_enlaces && <p className="visor3d-aviso">{AVISO_SIN_ENLACES}</p>}
          <dl className="visor3d-datos">
            <dt>Fichero</dt>
            <dd>{molecula.origen}</dd>
            {molecula.posicion !== null && (
              <>
                <dt>Posición</dt>
                <dd>nº {molecula.posicion}</dd>
              </>
            )}
            <dt>Átomos</dt>
            <dd>{molecula.num_atomos ?? '—'}</dd>
            {molecula.campos.map((c, i) => <Campo key={i} nombre={c.nombre} valor={c.valor} />)}
          </dl>
          <div className="visor3d-hueco-acciones">
            <button className="btn-descarga" onClick={alDescargar}>
              <Icono nombre="bajar" />Descargar
            </button>
            <button className="btn-borrar" onClick={alVaciar} aria-label={`Vaciar el hueco ${hueco}`}>
              <Icono nombre="cerrar" />Vaciar
            </button>
          </div>
        </>
      )}
    </section>
  )
}
