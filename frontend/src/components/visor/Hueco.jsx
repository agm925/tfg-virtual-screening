import { useState } from 'react'
import { recortar, ESTILOS, estiloEfectivo } from '../../utils/visor'
import Icono from '../Icono'
import { useIdioma } from '../../hooks/useIdioma'

// Un campo del registro (RF-10). El valor lo escribió quien subió el fichero:
// va siempre como texto de React, nunca como HTML (RNF-2). Si es largo se
// enseña el principio y se puede ver entero.
function Campo({ nombre, valor }) {
  const { t } = useIdioma()
  const [entero, setEntero] = useState(false)
  const { corto, completo, recortado } = recortar(valor)
  return (
    <>
      <dt>{nombre}</dt>
      <dd>
        <span className="visor3d-valor">{entero ? completo : corto}{recortado && !entero && '…'}</span>
        {recortado && (
          <button className="btn-enlace visor3d-ver-completo" onClick={() => setEntero(!entero)}>
            {entero ? t('visor.ver_menos') : t('visor.ver_completo')}
          </button>
        )}
      </dd>
    </>
  )
}

// Cómo se dibuja la molécula del hueco (RF-9). Si se piden cintas para algo
// que el fichero no declara como proteína, se dice por qué se ve en varillas.
function SelectorEstilo({ hueco, molecula, estilo, alCambiar }) {
  const { t } = useIdioma()
  const { estilo: efectivo, aviso } = estiloEfectivo(estilo, molecula)
  const id = `visor-estilo-${hueco}`
  return (
    <div className="visor3d-estilo">
      <label htmlFor={id} className="visor3d-etiqueta">{t('visor.representacion')}</label>
      <select id={id} className="visor3d-campo" value={estilo ?? efectivo}
              onChange={e => alCambiar(e.target.value)}>
        {ESTILOS.map(e => <option key={e.valor} value={e.valor}>{t(e.etiqueta)}</option>)}
      </select>
      {aviso && <p className="visor3d-aviso" role="status">{t(aviso)}</p>}
    </div>
  )
}

// El panel de un hueco (A o B, RF-4): su color, si es el activo, qué
// molécula tiene y sus datos (RF-10), y la descarga (RF-11).
export default function Hueco({ hueco, molecula, estilo, activo, alActivar, alVaciar, alDescargar, alCambiarEstilo }) {
  const { t } = useIdioma()
  return (
    <section className={`panel visor3d-hueco hueco-${hueco.toLowerCase()} ${activo ? 'activo' : ''}`}
             aria-label={t('visor.molecula_hueco', { hueco })}>
      <div className="visor3d-hueco-cabecera">
        <h3><span className="visor3d-muestra" aria-hidden="true" />{t('visor.molecula_hueco', { hueco })}</h3>
        {activo ? (
          <span className="visor3d-activo">{t('visor.hueco_activo')}</span>
        ) : (
          <button className="btn-enlace" onClick={alActivar}>{t('visor.usar_hueco')}</button>
        )}
      </div>

      {!molecula && (
        <p className="texto-secundario">
          {t('visor.vacio')}{activo && ` ${t('visor.vacio_activo')}`}
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
          {/* Avisos sobre cómo se ve la molécula (RF-12), en lenguaje llano. */}
          {molecula.dibujable && molecula.solo_2d && <p className="visor3d-aviso">{t('visor.aviso_2d')}</p>}
          {molecula.dibujable && molecula.sin_enlaces && <p className="visor3d-aviso">{t('visor.aviso_sin_enlaces')}</p>}
          <dl className="visor3d-datos">
            <dt>{t('visor.fichero')}</dt>
            <dd>{molecula.origen}</dd>
            {molecula.posicion !== null && (
              <>
                <dt>{t('visor.posicion')}</dt>
                <dd>{t('visor.numero', { n: molecula.posicion })}</dd>
              </>
            )}
            <dt>{t('visor.atomos')}</dt>
            <dd>{molecula.num_atomos ?? '—'}</dd>
            {molecula.campos.map((c, i) => <Campo key={i} nombre={c.nombre} valor={c.valor} />)}
          </dl>
          <div className="visor3d-hueco-acciones">
            <button className="btn-descarga" onClick={alDescargar}>
              <Icono nombre="bajar" />{t('comun.descargar')}
            </button>
            <button className="btn-borrar" onClick={alVaciar} aria-label={t('visor.vaciar_hueco', { hueco })}>
              <Icono nombre="cerrar" />{t('visor.vaciar')}
            </button>
          </div>
        </>
      )}
    </section>
  )
}
