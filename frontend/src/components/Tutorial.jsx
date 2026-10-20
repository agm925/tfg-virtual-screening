import { useState } from 'react';
import Icono from './Icono';
import TextoConFormato from './TextoConFormato';
import { tipoNodo, TIPOS_NODO, ETIQUETA_ALGORITMO } from '../utils/tiposNodo';
import { traducir } from '../utils/idioma';
import { useIdioma } from '../hooks/useIdioma';
import tutorialEs from '../textos/tutorial.es.js';
import tutorialEn from '../textos/tutorial.en.js';
import '../styles/Nodos.css';
import '../styles/Tutorial.css';

// Tutorial (spec 003). Mismo aspecto que el resto de la aplicación, y los
// iconos, nombres y colores de los nodos salen de utils/tiposNodo.js: si
// allí cambia un nombre o un color, aquí cambia solo. Se escribe para un
// biólogo, así que no habla de cómo está montada la plataforma (programas
// instalados, cola de trabajos): eso es cosa del administrador.
//
// La prosa está en textos/tutorial.es.js y tutorial.en.js (spec 014, R6), con
// las negritas marcadas con **…**; aquí solo queda la estructura.

const SECCIONES = [
  { id: 'plataforma', icono: 'grafico' },
  { id: 'moleculas',  icono: 'matraz' },
  { id: 'algoritmos', icono: 'codigo' },
  { id: 'constructor', icono: 'nodos' },
  { id: 'nodos',      icono: 'bloques' },
  { id: 'flujo',      icono: 'reproducir' },
  { id: 'visor',      icono: 'cubo' },
  { id: 'consejos',   icono: 'bombilla' },
];

const DICCIONARIOS = { es: tutorialEs, en: tutorialEn };

// Los pasos del flujo habitual, con el color de cada familia de nodo.
const FLUJO = ['upload', 'preprocesado', 'comparacion', 'docking', 'descargar'];

const PASOS_EJEMPLO = [1, 2, 3, 4, 5, 6];
const ERRORES = [1, 2, 3, 4, 5, 6, 7];
const CONSEJOS = [1, 2, 3, 4, 5, 6, 7, 8];

// Los tipos de algoritmo, con lo que hace cada uno y los del catálogo.
const TIPOS_ALGORITMO = ['preprocesado', 'alineacion', 'comparacion', 'docking'];

// Los nodos de la sección «Tipos de nodo»: qué reciben y qué entregan, si lo
// dicen (clave del diccionario), y si son opcionales.
const NODOS = [
  { tipo: 'upload', salida: true },
  { tipo: 'selectMol', salida: true },
  { tipo: 'selectDB', salida: true },
  { tipo: 'preprocesado', entradas: true, salida: true },
  { tipo: 'alineacion', entradas: true, salida: true },
  { tipo: 'comparacion', entradas: true, salida: true },
  { tipo: 'docking', entradas: true, salida: true },
  { tipo: 'ejecutar', opcional: true },
  { tipo: 'descargar', opcional: true, entradas: true },
];

const Titulo = ({ icono, children }) => (
  <h2><Icono nombre={icono} tamano={22} />{children}</h2>
);

const Aviso = ({ icono = 'aviso', variante = '', children }) => (
  <div className={`tutorial-aviso ${variante}`}>
    <Icono nombre={icono} tamano={18} />
    <div>{children}</div>
  </div>
);

const Boton = ({ icono, children }) => (
  <span className="tutorial-boton">{icono && <Icono nombre={icono} tamano={15} />}{children}</span>
);

// Un tipo de nodo, con el icono y el color que tiene en el Constructor. `tt`
// y `nombres` los da el tutorial, en el idioma de la interfaz.
const Nodo = ({ tt, nombres, tipo, opcional, entradas, salida }) => {
  const { familia, icono } = tipoNodo(tipo);
  return (
    <article className={`tutorial-nodo familia-${familia}`}>
      <div className="tutorial-nodo-cabecera">
        <Icono nombre={icono} tamano={18} />{nombres[tipo]}
        {opcional && <span className="tutorial-nodo-opcional">{tt('nodo.opcional')}</span>}
      </div>
      <div className="tutorial-nodo-cuerpo">
        <p>{tt(`nodos.${tipo}`)}</p>
        {entradas && <p><strong>{tt('nodo.recibe')}</strong> {tt(`nodos.${tipo}_recibe`)}</p>}
        {salida && <p><strong>{tt('nodo.entrega')}</strong> {tt(`nodos.${tipo}_entrega`)}</p>}
      </div>
    </article>
  );
};

// El tipo de un algoritmo, con el color de su nodo.
const TipoAlgoritmo = ({ nombres, tipo }) => {
  const { familia, icono } = tipoNodo(tipo);
  return (
    <span className={`tutorial-tipo familia-${familia}`}>
      <Icono nombre={icono} tamano={14} />{nombres[`tipo_${tipo}`]}
    </span>
  );
};

export default function Tutorial() {
  const { t, idioma } = useIdioma();
  const [seccionAbierta, setSeccionAbierta] = useState('plataforma');

  // Los nombres de los nodos y de los tipos de algoritmo, tal como los ve el
  // usuario en la paleta, para rellenar {selectMol}, {tipo_docking}…
  const nombres = Object.fromEntries([
    ...TIPOS_NODO.map(n => [n.tipo, t(n.etiqueta)]),
    ...Object.entries(ETIQUETA_ALGORITMO).map(([tipo, clave]) => [`tipo_${tipo}`, t(clave)]),
  ]);
  const tt = (clave) => traducir(idioma, clave, nombres, DICCIONARIOS);
  // Un texto con sus **negritas**.
  const f = (clave) => <TextoConFormato texto={tt(clave)} />;

  return (
    <div className="seccion-wrapper tutorial-pagina">
      <h2>{tt('titulo')}</h2>
      <p className="seccion-subtitulo">{tt('subtitulo')}</p>

      <div className="tutorial-layout">
        <nav className="tutorial-indice" aria-label={tt('indice')}>
          {SECCIONES.map(s => (
            <button
              key={s.id}
              className="tutorial-indice-btn"
              aria-current={seccionAbierta === s.id ? 'true' : undefined}
              onClick={() => setSeccionAbierta(s.id)}
            >
              <Icono nombre={s.icono} tamano={18} />{tt(`seccion.${s.id}`)}
            </button>
          ))}
        </nav>

        <div className="tutorial-contenido">

          {/* 1. VISIÓN GENERAL */}
          {seccionAbierta === 'plataforma' && (
            <section className="tutorial-seccion">
              <Titulo icono="grafico">{tt('plataforma.titulo')}</Titulo>
              <p>{f('plataforma.intro')}</p>

              <div className="tutorial-tarjetas">
                {[['moleculas', 'matraz'], ['algoritmos', 'codigo'], ['constructor', 'nodos'],
                  ['resultados', 'grafico'], ['visor', 'cubo']].map(([id, icono]) => (
                  <div key={id} className="tutorial-tarjeta">
                    <h3><Icono nombre={icono} />{tt(`plataforma.${id}_titulo`)}</h3>
                    <p>{tt(`plataforma.${id}`)}</p>
                  </div>
                ))}
              </div>

              <h3>{tt('plataforma.flujo_titulo')}</h3>
              <ol className="tutorial-flujo">
                {FLUJO.map(tipo => {
                  const { familia, icono } = tipoNodo(tipo);
                  return (
                    <li key={tipo}>
                      <span className={`tutorial-flujo-paso familia-${familia}`}>
                        <Icono nombre={icono} tamano={16} />{nombres[tipo]}
                      </span>
                    </li>
                  );
                })}
              </ol>

              <Aviso icono="reloj" variante="ok">{f('plataforma.cola')}</Aviso>
            </section>
          )}

          {/* 2. MOLÉCULAS */}
          {seccionAbierta === 'moleculas' && (
            <section className="tutorial-seccion">
              <Titulo icono="matraz">{tt('moleculas.titulo')}</Titulo>
              <p>{f('moleculas.intro')}</p>
              <p>{f('moleculas.visibilidad')}</p>

              <h3>{tt('moleculas.tipos_titulo')}</h3>
              <div className="tutorial-tabla-contenedor">
                <table className="tutorial-tabla">
                  <thead>
                    <tr><th>{tt('moleculas.col_tipo')}</th><th>{tt('moleculas.col_formatos')}</th><th>{tt('moleculas.col_para')}</th></tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>{tt('moleculas.individual')}</td>
                      <td><code>.sdf</code>, <code>.mol</code>, <code>.mol2</code>, <code>.pdb</code>, <code>.pdbqt</code>, <code>.xyz</code>, <code>.smi</code></td>
                      <td>{tt('moleculas.individual_para')}</td>
                    </tr>
                    <tr>
                      <td>{tt('moleculas.biblioteca')}</td>
                      <td><code>.sdf</code> {tt('moleculas.biblioteca_formato')}</td>
                      <td>{tt('moleculas.biblioteca_para')}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <h3>{tt('moleculas.subir_titulo')}</h3>
              <ol className="tutorial-pasos">
                {[1, 2, 3, 4, 5].map(n => <li key={n}>{f(`moleculas.paso${n}`)}</li>)}
              </ol>

              <Aviso icono="matraz">{f('moleculas.cuenta')}</Aviso>

              <h3>{tt('moleculas.acciones_titulo')}</h3>
              <p>{f('moleculas.acciones')}</p>

              <h3>{tt('moleculas.constructor_titulo')}</h3>
              <p>{tt('moleculas.constructor')}</p>
            </section>
          )}

          {/* 3. ALGORITMOS */}
          {seccionAbierta === 'algoritmos' && (
            <section className="tutorial-seccion">
              <Titulo icono="codigo">{tt('algoritmos.titulo')}</Titulo>
              <p>{f('algoritmos.intro')}</p>

              <h3>{tt('algoritmos.tipos_titulo')}</h3>
              <div className="tutorial-tabla-contenedor">
                <table className="tutorial-tabla">
                  <thead>
                    <tr><th>{tt('algoritmos.col_tipo')}</th><th>{tt('algoritmos.col_hace')}</th><th>{tt('algoritmos.col_ejemplos')}</th></tr>
                  </thead>
                  <tbody>
                    {TIPOS_ALGORITMO.map(tipo => (
                      <tr key={tipo}>
                        <td><TipoAlgoritmo nombres={nombres} tipo={tipo} /></td>
                        <td>{tt(`algoritmos.${tipo}`)}</td>
                        <td>{tt(`algoritmos.${tipo}_ejemplos`)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <h3>{tt('algoritmos.subir_titulo')}</h3>
              <ol className="tutorial-pasos">
                {[1, 2, 3, 4, 5].map(n => <li key={n}>{f(`algoritmos.paso${n}`)}</li>)}
              </ol>

              <Aviso variante="aviso">{tt('algoritmos.aviso')}</Aviso>
            </section>
          )}

          {/* 4. CONSTRUCTOR */}
          {seccionAbierta === 'constructor' && (
            <section className="tutorial-seccion">
              <Titulo icono="nodos">{tt('constructor.titulo')}</Titulo>
              <p>{f('constructor.intro')}</p>

              <h3>{tt('constructor.zonas_titulo')}</h3>
              <div className="tutorial-zonas">
                {[['paleta', 'bloques'], ['lienzo', 'nodos'], ['resultados', 'grafico']].map(([id, icono]) => (
                  <div key={id} className="tutorial-zona">
                    <h4><Icono nombre={icono} />{tt(`constructor.${id}_titulo`)}</h4>
                    <p>{f(`constructor.${id}`)}</p>
                  </div>
                ))}
              </div>

              <h3>{tt('constructor.barra_titulo')}</h3>
              <div className="tutorial-tabla-contenedor">
                <table className="tutorial-tabla">
                  <thead>
                    <tr><th>{tt('constructor.col_boton')}</th><th>{tt('constructor.col_hace')}</th></tr>
                  </thead>
                  <tbody>
                    {[['nuevo', 'mas'], ['guardar', 'guardar'], ['limpiar', 'papelera'], ['cargar', null],
                      ['ejecutar', 'reproducir']].map(([id, icono]) => (
                      <tr key={id}>
                        <td><Boton icono={icono}>{tt(`constructor.${id}`)}</Boton></td>
                        <td>{tt(`constructor.${id}_hace`)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <Aviso icono="ok" variante="ok">{f('constructor.guardado_auto')}</Aviso>

              <h3>{tt('constructor.eliminar_titulo')}</h3>
              <p>{f('constructor.eliminar')}</p>

              <h3>{tt('constructor.conectar_titulo')}</h3>
              <ol className="tutorial-pasos">
                {[1, 2, 3, 4].map(n => <li key={n}>{f(`constructor.conectar${n}`)}</li>)}
              </ol>
              <Aviso icono="bombilla">{tt('constructor.zoom')}</Aviso>

              <h3>{tt('constructor.catalogo_titulo')}</h3>
              <p>{tt('constructor.catalogo')}</p>

              <h3>{tt('constructor.cribado_titulo')}</h3>
              <p>{f('constructor.cribado')}</p>
            </section>
          )}

          {/* 5. TIPOS DE NODO */}
          {seccionAbierta === 'nodos' && (
            <section className="tutorial-seccion">
              <Titulo icono="bloques">{tt('nodos.titulo')}</Titulo>
              <p>{tt('nodos.intro')}</p>
              <div className="tutorial-nodos">
                {NODOS.map(n => <Nodo key={n.tipo} tt={tt} nombres={nombres} {...n} />)}
              </div>
            </section>
          )}

          {/* 6. EJEMPLO PASO A PASO */}
          {seccionAbierta === 'flujo' && (
            <section className="tutorial-seccion">
              <Titulo icono="reproducir">{tt('flujo.titulo')}</Titulo>
              <p>{tt('flujo.intro')}</p>

              <ol className="tutorial-ejemplo">
                {PASOS_EJEMPLO.map(n => (
                  <li key={n}>
                    <span className="tutorial-ejemplo-numero" aria-hidden="true">{n}</span>
                    <div>
                      <h4>{tt(`flujo.paso${n}`)}</h4>
                      <p>{tt(`flujo.paso${n}_detalle`)}</p>
                    </div>
                  </li>
                ))}
              </ol>

              <Aviso icono="bombilla">{tt('flujo.opcionales')}</Aviso>
            </section>
          )}

          {/* 7. VISOR 3D */}
          {seccionAbierta === 'visor' && (
            <section className="tutorial-seccion">
              <Titulo icono="cubo">{tt('visor.titulo')}</Titulo>
              <p>{tt('visor.intro')}</p>

              <h3>{tt('visor.elegir_titulo')}</h3>
              <p>{tt('visor.elegir')}</p>

              <h3>{tt('visor.huecos_titulo')}</h3>
              <p>{f('visor.huecos')}</p>
              <ul className="tutorial-consejos">
                <li>{f('visor.superpuestas')}</li>
                <li>{f('visor.lado_a_lado')}</li>
              </ul>

              <h3>{tt('visor.mirar_titulo')}</h3>
              <p>{f('visor.mirar')}</p>

              <h3>{tt('visor.datos_titulo')}</h3>
              <p>{f('visor.datos')}</p>

              <h3>{tt('visor.otras_titulo')}</h3>
              <p>{f('visor.otras')}</p>

              <Aviso variante="aviso">{tt('visor.no_dibuja')}</Aviso>
            </section>
          )}

          {/* 8. CONSEJOS Y ERRORES */}
          {seccionAbierta === 'consejos' && (
            <section className="tutorial-seccion">
              <Titulo icono="bombilla">{tt('consejos.titulo')}</Titulo>

              <h3>{tt('consejos.consejos_titulo')}</h3>
              <ul className="tutorial-consejos">
                {CONSEJOS.map(n => <li key={n}>{f(`consejos.${n}`)}</li>)}
              </ul>

              {/* Solo lo que un biólogo puede resolver desde la interfaz. Lo que
                  depende de cómo esté montada la plataforma es cosa del
                  administrador y aquí solo se dice que se le avise (principio 7). */}
              <h3>{tt('errores.titulo')}</h3>
              <div className="tutorial-errores">
                {ERRORES.map(n => (
                  <div key={n} className="tutorial-error">
                    <h4><Icono nombre="error" />{tt(`errores.${n}_titulo`)}</h4>
                    <p>{tt(`errores.${n}`)}</p>
                  </div>
                ))}
              </div>
            </section>
          )}

        </div>
      </div>
    </div>
  );
}
