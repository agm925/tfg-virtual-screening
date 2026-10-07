import { useEffect, useRef, useState } from 'react'
import Icono from '../Icono'
import { modoDisponible, estiloEfectivo } from '../../utils/visor'

// El formato de cada fichero para la librería 3D (3Dmol). Un .mol es un
// registro SDF suelto.
const FORMATO_3DMOL = { sdf: 'sdf', mol: 'sdf', mol2: 'mol2', pdb: 'pdb', pdbqt: 'pdbqt', xyz: 'xyz' }

// La librería se carga en index.html (excepción de los principios 1 y 3);
// normalmente ya está, pero se espera un poco por si la red va lenta.
async function libreria3D() {
  for (let i = 0; i < 25 && !window.$3Dmol; i += 1) {
    await new Promise(r => setTimeout(r, 200))
  }
  return window.$3Dmol || null
}

// Si el navegador puede dibujar en 3D. Sin WebGL (aceleración gráfica
// desactivada o no compatible) la librería no dibuja nada y no avisa.
//
// Se pregunta una sola vez y se suelta el contexto de prueba: antes se creaba
// uno en cada render, y al pasar de unos 16 el navegador descarta los más
// antiguos, que pueden ser los del propio visor ("Too many active WebGL
// contexts", comprobaciones.md).
let webGLDisponible = null
function hayWebGL() {
  if (webGLDisponible === null) {
    try {
      const contexto = document.createElement('canvas').getContext('webgl')
      webGLDisponible = Boolean(contexto)
      contexto?.getExtension('WEBGL_lose_context')?.loseContext()
    } catch {
      webGLDisponible = false
    }
  }
  return webGLDisponible
}

// Fracción del visor que ocupa la molécula recién encuadrada.
const MARGEN_ENCUADRE = 0.85

const SIN_WEBGL ='Este navegador no puede dibujar en 3D: la aceleración gráfica está desactivada o no es '
  + 'compatible. Puedes seguir viendo los datos de cada molécula y descargarla.'
const NADA_QUE_DIBUJAR = 'Esta molécula no se puede dibujar: el motivo está en su panel, debajo.'
const NINGUNA_SE_DIBUJA = 'Ninguna de las dos moléculas se puede dibujar: el motivo está en el panel de cada una, debajo.'

// El color de los carbonos de cada hueco sale de tokens.css (--hueco-a,
// --hueco-b): el mismo que el borde de su panel, con una sola fuente
// (decisión D11 del plan).
function colorDelHueco(hueco) {
  return getComputedStyle(document.documentElement).getPropertyValue(`--hueco-${hueco.toLowerCase()}`).trim()
}

// Colores por elemento de siempre (oxígeno rojo, nitrógeno azul...), salvo el
// carbono, que lleva el color de su hueco: así se distinguen A y B sin perder
// la información de los elementos (RF-7).
function coloresDe($3Dmol, hueco) {
  return { prop: 'elem', map: { ...$3Dmol.elementColors.Jmol, C: colorDelHueco(hueco) } }
}

// Cómo se dibuja cada estilo (RF-9) en la librería 3D.
function aplicarEstilo($3Dmol, v, modelo, estilo, hueco) {
  const colorscheme = coloresDe($3Dmol, hueco)
  if (estilo === 'esferas') {
    modelo.setStyle({}, { sphere: { colorscheme } })
  } else if (estilo === 'cintas') {
    // La cadena en el color del hueco; lo que no es cadena (ligandos, agua,
    // iones que trae el fichero) sigue en varillas para que no desaparezca.
    modelo.setStyle({}, { cartoon: { color: colorDelHueco(hueco) } })
    modelo.setStyle({ hetflag: true }, { stick: { radius: 0.15, colorscheme } })
  } else if (estilo === 'superficie') {
    modelo.setStyle({}, { stick: { radius: 0.1, colorscheme } })
    v.addSurface($3Dmol.SurfaceType.VDW, { opacity: 0.7, color: colorDelHueco(hueco) }, { model: modelo })
  } else {
    modelo.setStyle({}, { stick: { radius: 0.18, colorscheme }, sphere: { scale: 0.25, colorscheme } })
  }
}

// Un visor 3D con las moléculas que se le pasan. Es la única pieza que habla
// con la librería 3D (plan, sección 1.2).
function Escena({ capas }) {
  const contenedor = useRef(null)
  const visor = useRef(null)
  // La vista recién encuadrada (giro, acercamiento y desplazamiento), para
  // volver a ella: zoomTo solo reencuadra y conserva el giro del usuario.
  const vistaInicial = useRef(null)
  const [sinLibreria, setSinLibreria] = useState(false)

  // Lo que se dibuja: cambia cuando cambia alguna molécula.
  const firma = capas.map(c => `${c.hueco}:${c.molecula.origen}#${c.molecula.posicion}:${c.estilo}`).join('|')

  useEffect(() => {
    let vigente = true
    ;(async () => {
      const $3Dmol = await libreria3D()
      if (!vigente) return
      if (!$3Dmol) { setSinLibreria(true); return }
      if (!visor.current) {
        visor.current = $3Dmol.createViewer(contenedor.current, { backgroundColor: 'white' })
      }
      const v = visor.current
      v.removeAllSurfaces()
      v.clear()
      // Superpuestas: cada una con sus coordenadas del fichero, sin moverlas
      // ni alinearlas (RF-8).
      for (const { hueco, molecula, estilo } of capas) {
        const modelo = v.addModel(molecula.contenido, FORMATO_3DMOL[molecula.formato])
        aplicarEstilo($3Dmol, v, modelo, estilo, hueco)
      }
      // Al tamaño real del contenedor antes de encuadrar: al cambiar de modo,
      // el visor puede crearse antes de que la rejilla le dé su ancho final.
      v.resize()
      v.zoomTo()
      // zoomTo encuadra con la altura del visor: en uno más alto que ancho
      // (lado a lado, móvil) una molécula alargada se salía por los lados. Se
      // aleja en esa proporción para que quepa también a lo ancho, y un poco
      // más: zoomTo ajusta la esfera de los átomos al borde justo, y con la
      // perspectiva los átomos más cercanos se ven mayores y quedaban cortados
      // (comprobaciones.md, C24).
      const { width, height } = contenedor.current.getBoundingClientRect()
      if (width > 0 && height > 0) v.zoom(MARGEN_ENCUADRE * Math.min(1, width / height))
      v.render()
      vistaInicial.current = v.getView()
    })()
    return () => { vigente = false }
    // `firma` resume `capas`: redibujar solo si cambia lo que hay que dibujar.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firma])

  // El tamaño del visor cambia con la ventana y con la maquetación (pasar a
  // lado a lado, apilarse en pantallas estrechas): se sigue al contenedor, no
  // solo a la ventana.
  useEffect(() => {
    const observador = new ResizeObserver(() => {
      visor.current?.resize()
      visor.current?.render()
    })
    observador.observe(contenedor.current)
    return () => observador.disconnect()
  }, [])

  const volverAVistaInicial = () => {
    if (!visor.current || !vistaInicial.current) return
    visor.current.setView(vistaInicial.current)
    visor.current.render()
  }

  return (
    <div className="visor3d-escena">
      <div ref={contenedor} className="visor3d-escena-dibujo" />
      {sinLibreria && (
        <p className="visor3d-lienzo-vacio" role="status">
          No se ha podido cargar el dibujo 3D. Comprueba la conexión y recarga la página.
        </p>
      )}
      <div className="visor3d-escena-controles">
        <button className="btn-secundario" onClick={volverAVistaInicial}>
          <Icono nombre="procesando" />Vista inicial
        </button>
      </div>
    </div>
  )
}

// El lienzo del visor (RF-7, RF-8): las moléculas de los huecos ocupados que
// se pueden dibujar, juntas en un visor o cada una en el suyo, o el mensaje de
// que no hay ninguna.
export default function LienzoVisor({ estado }) {
  const capas = ['A', 'B']
    .filter(h => estado.huecos[h]?.dibujable)
    .map(h => ({
      hueco: h,
      molecula: estado.huecos[h],
      estilo: estiloEfectivo(estado.estilos[h], estado.huecos[h]).estilo,
    }))

  if (estado.huecos.A === null && estado.huecos.B === null) {
    return <p className="visor3d-lienzo-vacio">Elige una molécula para el hueco A</p>
  }
  if (!hayWebGL()) {
    return <p className="visor3d-lienzo-vacio" role="status">{SIN_WEBGL}</p>
  }

  // Lado a lado: un visor por hueco, cada uno manejado por su cuenta (girar o
  // acercar uno no mueve el otro).
  if (estado.modo === 'lado_a_lado' && modoDisponible(estado)) {
    return (
      <div className="visor3d-lado-a-lado">
        {['A', 'B'].map(h => (
          <div key={h} className={`visor3d-panel-escena hueco-${h.toLowerCase()}`}>
            <span className="visor3d-etiqueta-escena">Molécula {h}</span>
            {estado.huecos[h].dibujable
              ? <Escena capas={capas.filter(c => c.hueco === h)} />
              : <p className="visor3d-lienzo-vacio" role="status">{NADA_QUE_DIBUJAR}</p>}
          </div>
        ))}
      </div>
    )
  }
  if (capas.length === 0) {
    const dos = estado.huecos.A !== null && estado.huecos.B !== null
    return <p className="visor3d-lienzo-vacio" role="status">{dos ? NINGUNA_SE_DIBUJA : NADA_QUE_DIBUJAR}</p>
  }
  return <Escena capas={capas} />
}
