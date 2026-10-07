import { useState } from 'react';
import Icono from './Icono';
import { tipoNodo, ETIQUETA_ALGORITMO } from '../utils/tiposNodo';
import '../styles/Nodos.css';
import '../styles/Tutorial.css';

// Tutorial (spec 003). Mismo aspecto que el resto de la aplicación, y los
// iconos, nombres y colores de los nodos salen de utils/tiposNodo.js: si
// allí cambia un nombre o un color, aquí cambia solo. Se escribe para un
// biólogo, así que no habla de cómo está montada la plataforma (programas
// instalados, cola de trabajos): eso es cosa del administrador.

const SECCIONES = [
  { id: 'plataforma', icono: 'grafico',   titulo: 'Visión general' },
  { id: 'moleculas',  icono: 'matraz',    titulo: 'Moléculas' },
  { id: 'algoritmos', icono: 'codigo',    titulo: 'Algoritmos' },
  { id: 'constructor', icono: 'nodos',     titulo: 'Constructor' },
  { id: 'nodos',      icono: 'bloques',   titulo: 'Tipos de nodo' },
  { id: 'flujo',      icono: 'reproducir', titulo: 'Ejemplo paso a paso' },
  { id: 'visor',      icono: 'cubo',      titulo: 'Visor 3D' },
  { id: 'consejos',   icono: 'bombilla',  titulo: 'Consejos y errores' },
];

// El nombre con que se ve el nodo en el Constructor.
const nombre = (tipo) => tipoNodo(tipo).etiqueta;

const Titulo = ({ icono, children }) => (
  <h2><Icono nombre={icono} tamano={22} />{children}</h2>
);

const Aviso = ({ icono = 'aviso', variante = '', children }) => (
  <div className={`tutorial-aviso ${variante}`}>
    <Icono nombre={icono} tamano={18} />
    <div>{children}</div>
  </div>
);

// Un tipo de nodo, con el icono y el color que tiene en el Constructor.
const Nodo = ({ tipo, opcional = false, entradas, salida, children }) => {
  const { etiqueta, familia, icono } = tipoNodo(tipo);
  return (
    <article className={`tutorial-nodo familia-${familia}`}>
      <div className="tutorial-nodo-cabecera">
        <Icono nombre={icono} tamano={18} />{etiqueta}
        {opcional && <span className="tutorial-nodo-opcional">Opcional</span>}
      </div>
      <div className="tutorial-nodo-cuerpo">
        <p>{children}</p>
        {entradas && <p><strong>Recibe:</strong> {entradas}</p>}
        {salida && <p><strong>Entrega:</strong> {salida}</p>}
      </div>
    </article>
  );
};

// El tipo de un algoritmo, con el color de su nodo.
const TipoAlgoritmo = ({ tipo }) => {
  const { familia, icono } = tipoNodo(tipo);
  return (
    <span className={`tutorial-tipo familia-${familia}`}>
      <Icono nombre={icono} tamano={14} />{ETIQUETA_ALGORITMO[tipo]}
    </span>
  );
};

const Boton = ({ icono, children }) => (
  <span className="tutorial-boton">{icono && <Icono nombre={icono} tamano={15} />}{children}</span>
);

// Los pasos del flujo habitual, con el color de cada familia de nodo.
const FLUJO = ['upload', 'preprocesado', 'comparacion', 'docking', 'descargar'];

const PASOS_EJEMPLO = [
  {
    titulo: 'Sube tus moléculas',
    detalle: 'Ve a Moléculas y sube los dos ficheros (.mol2 o .sdf) que quieres comparar. Quedan en la biblioteca y los puedes usar en todos tus workflows sin volver a subirlos.',
  },
  {
    titulo: 'Crea el workflow',
    detalle: 'Ve al Constructor y pulsa «Nuevo workflow». Escribe un nombre que te ayude a reconocerlo, por ejemplo «Comparación Tanimoto».',
  },
  {
    titulo: `Añade dos nodos «${nombre('selectMol')}»`,
    detalle: `Arrastra «${nombre('selectMol')}» desde la paleta dos veces. En cada uno elige una de las moléculas que subiste. Si no aparecen, pulsa «actualizar» dentro del nodo.`,
  },
  {
    titulo: `Añade un nodo «${nombre('comparacion')}»`,
    detalle: `Arrástralo al lienzo y, en su desplegable, elige «similaridadTanimoto».`,
  },
  {
    titulo: 'Conecta los nodos',
    detalle: `Une la salida (borde derecho) del primer «${nombre('selectMol')}» con el punto mol1 de «${nombre('comparacion')}» (a la izquierda) y la del segundo con el punto mol2 (abajo).`,
  },
  {
    titulo: 'Ejecuta el workflow',
    detalle: 'Pulsa «Ejecutar workflow». El botón pasa por «En cola…» mientras espera su turno y por «Procesando…» mientras trabaja. Al terminar aparece el panel de resultados con el valor de similitud y el fichero para descargarlo. También recibirás un correo.',
  },
];

const ERRORES = [
  {
    titulo: `El nodo «${nombre('selectDB')}» no ofrece ninguna biblioteca`,
    texto: `Todavía no hay ningún fichero SDF con varias moléculas. Súbelo desde la página Moléculas, vuelve al Constructor y pulsa «actualizar» dentro del nodo.`,
  },
  {
    titulo: '«No se ha elegido ninguna molécula» o «no tiene ninguna biblioteca elegida»',
    texto: `Hay un nodo «${nombre('selectMol')}» o «${nombre('selectDB')}» sin nada elegido. Ábrelo, escoge un fichero de la lista y vuelve a ejecutar.`,
  },
  {
    titulo: '«Sin entrada de molécula», «faltan las dos moléculas» o «se necesitan ligando y receptor»',
    texto: `A ese nodo le falta alguna conexión. Une la salida del nodo anterior con su punto de la izquierda. Un nodo «${nombre('comparacion')}» necesita dos moléculas, y un «${nombre('docking')}», el ligando a la izquierda y el receptor abajo.`,
  },
  {
    titulo: '«El algoritmo ha sido desactivado» o «es privado de otro usuario»',
    texto: 'El workflow usa un algoritmo que ya no está disponible para ti. Elige otro en el nodo, o pide a su autor que lo haga público.',
  },
  {
    titulo: 'El botón se queda mucho tiempo en «En cola…»',
    texto: 'Los trabajos se atienden por turnos y puede haber otros delante, sobre todo cribados de bibliotecas grandes. No hace falta esperar delante de la pantalla: recibirás un correo al terminar. Si pasa mucho tiempo sin que empiece, avisa al administrador.',
  },
  {
    titulo: 'En el Visor 3D, «esta molécula no se puede dibujar»',
    texto: `El fichero no trae coordenadas 3D (por ejemplo, un SMILES) o el registro está dañado. Pásalo por un nodo «${nombre('preprocesado')}» que genere el 3D y abre el resultado en el visor.`,
  },
  {
    titulo: 'Un error que no está en esta lista',
    texto: 'Si el mensaje habla de un programa que falta o de un fallo interno, no es algo que tengas que arreglar tú. Avisa al administrador e indícale el número de la ejecución, que aparece en la página Resultados.',
  },
];

export default function Tutorial() {
  const [seccionAbierta, setSeccionAbierta] = useState('plataforma');

  return (
    <div className="seccion-wrapper tutorial-pagina">
      <h2>Tutorial</h2>
      <p className="seccion-subtitulo">
        Todo lo que necesitas para hacer cribado virtual de forma sencilla.
      </p>

      <div className="tutorial-layout">
        <nav className="tutorial-indice" aria-label="Secciones del tutorial">
          {SECCIONES.map(s => (
            <button
              key={s.id}
              className="tutorial-indice-btn"
              aria-current={seccionAbierta === s.id ? 'true' : undefined}
              onClick={() => setSeccionAbierta(s.id)}
            >
              <Icono nombre={s.icono} tamano={18} />{s.titulo}
            </button>
          ))}
        </nav>

        <div className="tutorial-contenido">

          {/* 1. VISIÓN GENERAL */}
          {seccionAbierta === 'plataforma' && (
            <section className="tutorial-seccion">
              <Titulo icono="grafico">¿Qué es MolServer?</Titulo>
              <p>
                MolServer es una plataforma de <strong>cribado virtual</strong>: te permite analizar
                moléculas y predecir cuáles podrían ser buenos fármacos, sin escribir una sola línea
                de código. Funciona como una cinta de montaje visual: tú decides qué operaciones
                aplicar a tus moléculas y en qué orden, y la plataforma las ejecuta por ti.
              </p>

              <div className="tutorial-tarjetas">
                <div className="tutorial-tarjeta">
                  <h3><Icono nombre="matraz" />Moléculas</h3>
                  <p>Sube tus moléculas sueltas y tus bibliotecas (SDF con muchas moléculas). Son la
                    materia prima de todos los análisis.</p>
                </div>
                <div className="tutorial-tarjeta">
                  <h3><Icono nombre="codigo" />Algoritmos</h3>
                  <p>Los scripts científicos disponibles (conversión de formatos, filtro de Lipinski,
                    generación 3D, docking…). Puedes subir los tuyos.</p>
                </div>
                <div className="tutorial-tarjeta">
                  <h3><Icono nombre="nodos" />Constructor</h3>
                  <p>Diseña tu pipeline arrastrando bloques y conectándolos. La ejecución se pone en
                    una cola para no bloquear a otros usuarios.</p>
                </div>
                <div className="tutorial-tarjeta">
                  <h3><Icono nombre="grafico" />Resultados</h3>
                  <p>Encuentra los ficheros de tus workflows y cribados. Desde aquí también puedes
                    enviar una molécula a un algoritmo concreto, sin montar un pipeline.</p>
                </div>
                <div className="tutorial-tarjeta">
                  <h3><Icono nombre="cubo" />Visor 3D</h3>
                  <p>Mira en 3D una molécula, una biblioteca o un resultado, y compara dos moléculas
                    sin descargar nada.</p>
                </div>
              </div>

              <h3>Flujo habitual de trabajo</h3>
              <ol className="tutorial-flujo">
                {FLUJO.map(tipo => {
                  const { etiqueta, familia, icono } = tipoNodo(tipo);
                  return (
                    <li key={tipo}>
                      <span className={`tutorial-flujo-paso familia-${familia}`}>
                        <Icono nombre={icono} tamano={16} />{etiqueta}
                      </span>
                    </li>
                  );
                })}
              </ol>

              <Aviso icono="reloj" variante="ok">
                <strong>Cola de procesamiento:</strong> cuando varios usuarios ejecutan workflows a
                la vez, los trabajos esperan su turno. Al terminar recibirás un <strong>correo
                electrónico</strong> con el resultado: no hace falta quedarse mirando la pantalla.
              </Aviso>
            </section>
          )}

          {/* 2. MOLÉCULAS */}
          {seccionAbierta === 'moleculas' && (
            <section className="tutorial-seccion">
              <Titulo icono="matraz">Moléculas</Titulo>
              <p>
                Antes de montar un workflow tus moléculas tienen que estar en la plataforma. La
                página <strong>Moléculas</strong> es el almacén de todos los ficheros moleculares.
              </p>
              <p>
                Lo que subes forma una <strong>biblioteca compartida</strong>: lo ven todos los
                usuarios, pero solo tú (o un administrador) puede borrarlo. Lo que generan tus
                workflows, en cambio, es privado: solo lo ves tú.
              </p>

              <h3>Tipos de fichero que puedes subir</h3>
              <div className="tutorial-tabla-contenedor">
                <table className="tutorial-tabla">
                  <thead>
                    <tr><th>Tipo</th><th>Formatos</th><th>¿Para qué?</th></tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Molécula individual</td>
                      <td><code>.sdf</code>, <code>.mol</code>, <code>.mol2</code>, <code>.pdb</code>, <code>.pdbqt</code>, <code>.xyz</code>, <code>.smi</code></td>
                      <td>Ligandos, receptores y referencias cristalográficas</td>
                    </tr>
                    <tr>
                      <td>Biblioteca</td>
                      <td><code>.sdf</code> con varias moléculas</td>
                      <td>Colecciones de compuestos para cribar todos de una vez</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <h3>¿Cómo subir un fichero?</h3>
              <ol className="tutorial-pasos">
                <li>Ve a la página <strong>Moléculas</strong>.</li>
                <li>Elige el panel adecuado: <em>«Molécula individual»</em> o <em>«Biblioteca»</em>.</li>
                <li>Arrastra el fichero a la zona punteada, o haz clic en ella para buscarlo en tu equipo.</li>
                <li>Pulsa <strong>«Subir»</strong>. El fichero aparece en las tablas de abajo en unos segundos.</li>
              </ol>

              <Aviso icono="matraz">
                Al subirlo, la plataforma <strong>cuenta las moléculas</strong> del fichero y lo
                clasifica por su contenido: un SDF con una sola molécula se guarda como molécula
                individual, y uno con varias, como biblioteca, aunque lo hayas subido por el otro
                panel. Te lo dice en pantalla.
              </Aviso>

              <h3>Qué puedes hacer con cada fichero</h3>
              <p>
                Cada fila tiene tres botones: <strong>Ver en 3D</strong> (abre el Visor 3D),{' '}
                <strong>Descargar</strong> y <strong>Eliminar</strong>.
              </p>

              <h3>¿Cómo se usan en el Constructor?</h3>
              <p>
                Una vez subidos, están disponibles al momento: el nodo «{nombre('selectMol')}» lista
                tus moléculas y el nodo «{nombre('selectDB')}», tus bibliotecas. No hay que volver a
                subir nada.
              </p>
            </section>
          )}

          {/* 3. ALGORITMOS */}
          {seccionAbierta === 'algoritmos' && (
            <section className="tutorial-seccion">
              <Titulo icono="codigo">Algoritmos</Titulo>
              <p>
                Aquí se suben los <strong>scripts científicos</strong> que la plataforma puede
                ejecutar. Cada algoritmo es un archivo Python (<code>.py</code>); al subirlo eliges
                qué tipo de operación hace, y eso decide en qué nodo del Constructor aparece.
              </p>

              <h3>Tipos de algoritmo</h3>
              <div className="tutorial-tabla-contenedor">
                <table className="tutorial-tabla">
                  <thead>
                    <tr><th>Tipo</th><th>¿Qué hace?</th><th>Ejemplos disponibles</th></tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td><TipoAlgoritmo tipo="preprocesado" /></td>
                      <td>Prepara o filtra una molécula</td>
                      <td>preparacionObabel, filtroLipinski, filtroObabel, gen3dRDKit, limpiezaSDF</td>
                    </tr>
                    <tr>
                      <td><TipoAlgoritmo tipo="alineacion" /></td>
                      <td>Alinea o reorienta una o dos moléculas</td>
                      <td>alinear3D (O3A), alinearMCS, centerMol</td>
                    </tr>
                    <tr>
                      <td><TipoAlgoritmo tipo="comparacion" /></td>
                      <td>Compara dos moléculas y da un valor numérico</td>
                      <td>similaridadTanimoto, rmsdConformaciones</td>
                    </tr>
                    <tr>
                      <td><TipoAlgoritmo tipo="docking" /></td>
                      <td>Acopla un ligando en un receptor proteico</td>
                      <td>dockingSmina</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <h3>¿Cómo subir un algoritmo?</h3>
              <ol className="tutorial-pasos">
                <li>Ve a la página <strong>Algoritmos</strong>.</li>
                <li>En <em>«¿Qué hace el algoritmo?»</em> elige su tipo: {ETIQUETA_ALGORITMO.preprocesado},{' '}
                  {ETIQUETA_ALGORITMO.alineacion}, {ETIQUETA_ALGORITMO.comparacion} o {ETIQUETA_ALGORITMO.docking}.
                  Debajo verás qué recibe el script.</li>
                <li>Rellena el nombre y la descripción, y elige el archivo <code>.py</code> en tu equipo.</li>
                <li>Pulsa <strong>«Subir y validar»</strong>. La plataforma ejecuta el script sobre
                  moléculas de referencia, como corresponde al tipo elegido, antes de aceptarlo.</li>
                <li>Si todo es correcto, el algoritmo entra en el catálogo y cualquier usuario puede
                  usarlo desde el Constructor.</li>
              </ol>

              <Aviso variante="aviso">
                El script debe escribir su resultado en el fichero que recibe como último argumento y
                terminar sin errores. Si no lo hace, la subida se rechaza y verás el motivo.
              </Aviso>
            </section>
          )}

          {/* 4. CONSTRUCTOR */}
          {seccionAbierta === 'constructor' && (
            <section className="tutorial-seccion">
              <Titulo icono="nodos">¿Qué es el Constructor?</Titulo>
              <p>
                Es el <strong>editor visual de workflows</strong>. En lugar de lanzar los algoritmos
                uno a uno, montas un flujo completo de forma gráfica, conectando bloques (nodos)
                entre sí.
              </p>

              <h3>Las tres zonas de la pantalla</h3>
              <div className="tutorial-zonas">
                <div className="tutorial-zona">
                  <h4><Icono nombre="bloques" />Izquierda: paleta</h4>
                  <p>Los tipos de nodo disponibles. <strong>Arrástralos</strong> al lienzo para añadirlos.</p>
                </div>
                <div className="tutorial-zona">
                  <h4><Icono nombre="nodos" />Centro: lienzo</h4>
                  <p>Donde montas el workflow. Coloca, configura y conecta los nodos con flechas.</p>
                </div>
                <div className="tutorial-zona">
                  <h4><Icono nombre="grafico" />Derecha: resultados</h4>
                  <p>Aparece al ejecutar. Muestra el estado, los errores y los ficheros, con «Ver en 3D» y descarga.</p>
                </div>
              </div>

              <h3>Barra de herramientas</h3>
              <div className="tutorial-tabla-contenedor">
                <table className="tutorial-tabla">
                  <thead>
                    <tr><th>Botón</th><th>¿Qué hace?</th></tr>
                  </thead>
                  <tbody>
                    <tr><td><Boton icono="mas">Nuevo workflow</Boton></td><td>Crea un workflow vacío con el nombre que tú elijas.</td></tr>
                    <tr><td><Boton icono="guardar">Guardar</Boton></td><td>Guarda el diseño actual.</td></tr>
                    <tr><td><Boton icono="papelera">Limpiar</Boton></td><td>Quita todos los nodos del lienzo, sin borrar el workflow guardado.</td></tr>
                    <tr><td><Boton>Cargar workflow…</Boton></td><td>Abre un workflow guardado antes.</td></tr>
                    <tr>
                      <td><Boton icono="reproducir">Ejecutar workflow</Boton></td>
                      <td>
                        Guarda el diseño, pone el trabajo en la cola y muestra el progreso: primero
                        «En cola…», luego «Procesando…» y, al terminar, el panel de resultados.
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <Aviso icono="ok" variante="ok">
                <strong>Guardado automático:</strong> al pulsar «Ejecutar workflow», el diseño se
                guarda antes de empezar. Si el workflow no existe todavía, te pide un nombre y lo
                crea solo. Si sales del Constructor con cambios sin guardar, te lo pregunta.
              </Aviso>

              <h3>¿Cómo eliminar un nodo?</h3>
              <p>
                Cada nodo tiene un botón <strong>×</strong> en la esquina de su cabecera. Quita solo
                ese nodo y sus conexiones, sin tocar el resto.
              </p>

              <h3>¿Cómo conectar dos nodos?</h3>
              <ol className="tutorial-pasos">
                <li>Pasa el ratón por el borde <strong>derecho</strong> de un nodo hasta ver un
                  círculo: es su punto de salida.</li>
                <li>Haz <strong>clic y arrastra</strong> desde ese círculo.</li>
                <li>Suéltalo sobre el círculo del borde <strong>izquierdo</strong> del nodo
                  siguiente: es su punto de entrada.</li>
                <li>Aparece una línea que los une.</li>
              </ol>
              <Aviso icono="bombilla">
                Con la rueda del ratón haces zoom, y arrastrando el fondo mueves el lienzo. El
                minimapa de la esquina inferior derecha te ayuda a orientarte en workflows grandes.
              </Aviso>

              <h3>Los nodos usan lo que ya tienes en la plataforma</h3>
              <p>
                Los nodos «{nombre('preprocesado')}», «{nombre('alineacion')}», «{nombre('comparacion')}» y «{nombre('docking')}»
                ofrecen los algoritmos del catálogo de la página Algoritmos. «{nombre('selectMol')}» muestra
                tus ficheros de Moléculas y «{nombre('selectDB')}», tus bibliotecas. Pulsa
                <em> «actualizar»</em> dentro del nodo si acabas de subir algo.
              </p>

              <h3>Cribar toda una biblioteca</h3>
              <p>
                Si el workflow empieza en un nodo «{nombre('selectDB')}», se aplica a <strong>todas las
                moléculas de la biblioteca</strong>. Qué obtienes depende del último algoritmo: un
                ranking si puntúa (Tanimoto, RMSD), las mejores poses ordenadas por afinidad si es un
                docking, o las moléculas ya transformadas si prepara, alinea o filtra. Todos los
                ficheros aparecen en el panel de resultados.
              </p>
            </section>
          )}

          {/* 5. TIPOS DE NODO */}
          {seccionAbierta === 'nodos' && (
            <section className="tutorial-seccion">
              <Titulo icono="bloques">Tipos de nodo</Titulo>
              <p>
                Cada tipo de nodo hace una operación distinta y tiene el mismo icono y color que en
                la paleta del Constructor.
              </p>

              <div className="tutorial-nodos">
                <Nodo tipo="upload" salida="la molécula, para el nodo siguiente">
                  Sube desde tu equipo un fichero de molécula (.sdf, .mol2, .pdb…). Es la entrada
                  cuando el fichero es nuevo; si ya lo tienes en Moléculas, usa «{nombre('selectMol')}».
                </Nodo>
                <Nodo tipo="selectMol" salida="la molécula elegida">
                  Usa una molécula que ya subiste a Moléculas, sin volver a subirla. Pulsa
                  «actualizar» si acabas de subir una.
                </Nodo>
                <Nodo tipo="selectDB" salida="las moléculas de la biblioteca, una a una">
                  Aplica el workflow a todas las moléculas de una biblioteca SDF: un cribado. Pulsa
                  «actualizar» si acabas de subir una biblioteca.
                </Nodo>
                <Nodo tipo="preprocesado" entradas="una molécula (izquierda)"
                      salida="la molécula preparada, o los valores calculados (por ejemplo, Lipinski)">
                  Convierte de formato, añade hidrógenos a pH 7.4, genera coordenadas 3D, centra la
                  molécula, filtra por propiedades (Lipinski, Open Babel) o limpia un SDF con varias moléculas.
                </Nodo>
                <Nodo tipo="alineacion" entradas="una molécula y, si el algoritmo lo pide, una referencia"
                      salida="la molécula alineada (SDF)">
                  Superpone una molécula sobre una referencia en 3D: Open3DAlign (O3A) para una
                  alineación global, MCS para alinear por la subestructura común, o centrado.
                </Nodo>
                <Nodo tipo="comparacion" entradas="molécula 1 (punto mol1, izquierda) y molécula 2 (punto mol2, abajo)"
                      salida="un valor numérico (JSON)">
                  Compara dos moléculas: similitud Tanimoto (de 0 a 1) con huellas de Morgan, o RMSD en
                  Ångströms entre dos poses de la misma molécula.
                </Nodo>
                <Nodo tipo="docking" entradas="ligando (izquierda), receptor en PDBQT (abajo) y una referencia opcional (arriba)"
                      salida="las poses (SDF) y las energías de afinidad (JSON)">
                  Encaja el ligando en el sitio de unión del receptor con Smina. Configuras la función
                  de puntuación, la caja de búsqueda (automática sobre el ligando, sobre una
                  referencia o manual) y la exhaustiveness.
                </Nodo>
                <Nodo tipo="ejecutar" opcional>
                  Marca dónde empieza el workflow. No hace falta: el workflow funciona igual sin él.
                </Nodo>
                <Nodo tipo="descargar" opcional entradas="un fichero de cualquier nodo anterior">
                  Marca un fichero para tenerlo a mano. El panel de resultados ya ofrece el fichero de
                  cada nodo, así que solo lo necesitas si quieres destacar uno.
                </Nodo>
              </div>
            </section>
          )}

          {/* 6. EJEMPLO PASO A PASO */}
          {seccionAbierta === 'flujo' && (
            <section className="tutorial-seccion">
              <Titulo icono="reproducir">Ejemplo: comparar dos moléculas</Titulo>
              <p>
                Vamos a calcular la similitud de Tanimoto entre dos moléculas. Antes de empezar,
                ten los dos ficheros a mano: los subirás en el primer paso.
              </p>

              <ol className="tutorial-ejemplo">
                {PASOS_EJEMPLO.map((paso, i) => (
                  <li key={paso.titulo}>
                    <span className="tutorial-ejemplo-numero" aria-hidden="true">{i + 1}</span>
                    <div>
                      <h4>{paso.titulo}</h4>
                      <p>{paso.detalle}</p>
                    </div>
                  </li>
                ))}
              </ol>

              <Aviso icono="bombilla">
                No necesitas los nodos «{nombre('ejecutar')}» ni «{nombre('descargar')}»: el resultado
                aparece en el panel de la derecha sin ellos.
              </Aviso>
            </section>
          )}

          {/* 7. VISOR 3D */}
          {seccionAbierta === 'visor' && (
            <section className="tutorial-seccion">
              <Titulo icono="cubo">Visor 3D</Titulo>
              <p>
                El Visor 3D te deja mirar moléculas sin descargarlas ni abrir otro programa: una
                molécula suelta, un compuesto de una biblioteca, una pose de un docking, o dos moléculas
                a la vez para ver cómo encajan.
              </p>

              <h3>Elegir qué ver</h3>
              <p>
                Busca por nombre entre tus moléculas, las bibliotecas y los resultados de tus workflows
                terminados. Si eliges una biblioteca o un resultado con varias moléculas, se abre su
                lista, con su propio buscador: escribe un nombre, o un número. Con «25» ves la
                molécula nº 25 y las que tienen 25 en el nombre. La lista carga de 50 en 50 mientras
                te desplazas, así que bibliotecas enormes se abren enseguida. Las poses de un docking
                salen en el orden del ranking.
              </p>

              <h3>Los huecos A y B</h3>
              <p>
                Hay dos huecos, cada uno con su color. Lo que elijas va al <strong>hueco activo</strong>;
                cuando rellenas el A, el B pasa a ser el activo. Puedes cambiar de hueco, vaciarlo o
                poner la misma molécula en los dos. Con dos moléculas elige cómo verlas:
              </p>
              <ul className="tutorial-consejos">
                <li><strong>Superpuestas</strong> (por defecto): en el mismo visor, con los carbonos de
                  cada una del color de su hueco. Respeta las coordenadas de cada fichero: no las
                  alinea. Sirve, por ejemplo, para ver un ligando dentro de su receptor.</li>
                <li><strong>Lado a lado</strong>: dos visores independientes. Girar uno no mueve el otro.</li>
              </ul>

              <h3>Mirar la molécula</h3>
              <p>
                Gira arrastrando, acerca o aleja con la rueda y mueve arrastrando con la tecla Ctrl
                pulsada. <strong>Vista inicial</strong> vuelve al encuadre de partida. En cada hueco
                eliges la representación: varillas, esferas, cintas o superficie. Las proteínas se
                abren en cintas y lo demás en varillas; las cintas solo sirven para cadenas de proteína.
              </p>

              <h3>Datos y descarga</h3>
              <p>
                Junto a cada hueco ves el nombre, el fichero de origen, la posición dentro de la
                biblioteca, el número de átomos y los campos del registro (por ejemplo, la afinidad
                de un docking). <strong>Descargar</strong> te da esa molécula como un fichero suelto,
                con todos sus campos.
              </p>

              <h3>Desde otras páginas</h3>
              <p>
                El botón <strong>Ver en 3D</strong> de Inicio, Moléculas, Resultados y el Constructor
                te lleva al visor con ese fichero ya puesto en el hueco A, sin tocar lo que hubiera
                en el B. Si vas a otra página y vuelves, lo encuentras como lo dejaste.
              </p>

              <Aviso variante="aviso">
                Si una molécula no se puede dibujar (por ejemplo, un SMILES, que no trae coordenadas
                3D), el visor te explica por qué y sigue enseñando la del otro hueco.
              </Aviso>
            </section>
          )}

          {/* 8. CONSEJOS Y ERRORES */}
          {seccionAbierta === 'consejos' && (
            <section className="tutorial-seccion">
              <Titulo icono="bombilla">Consejos y errores frecuentes</Titulo>

              <h3>Consejos</h3>
              <ul className="tutorial-consejos">
                <li>
                  <strong>Sube tus moléculas antes de abrir el Constructor.</strong> Los nodos
                  «{nombre('selectMol')}» y «{nombre('selectDB')}» cargan la lista al abrirse. Si subes
                  un fichero después, pulsa «actualizar» dentro del nodo.
                </li>
                <li>
                  <strong>«Ejecutar workflow» guarda automáticamente.</strong> No hace falta pulsar
                  «Guardar» antes; la primera vez te pedirá un nombre para el workflow. Aun así,
                  puedes guardar cuando quieras para no perder el diseño.
                </li>
                <li>
                  <strong>Puedes cambiar de página o cerrar la pestaña mientras se ejecuta.</strong> La
                  plataforma sigue trabajando: al volver al Constructor verás cómo va o su resultado,
                  y los ficheros quedan en la página Resultados. También recibirás un correo al terminar.
                </li>
                <li>
                  <strong>Mira el resultado en 3D antes de descargarlo.</strong> «Ver en 3D» abre las
                  moléculas o las poses de un docking en el Visor 3D, en el orden del ranking.
                </li>
                <li>
                  <strong>Comprueba el Lipinski antes del docking.</strong> Si la molécula falla el
                  filtro (FAIL), el docking gastará tiempo con un compuesto que probablemente no
                  sea un buen candidato a fármaco.
                </li>
                <li>
                  <strong>El receptor del docking debe estar en PDBQT.</strong> Si lo tienes en PDB,
                  pásalo antes por un nodo «{nombre('preprocesado')}» con el algoritmo de preparación de
                  Open Babel y el formato de salida <em>PDBQT</em>, que añade los hidrógenos y las cargas.
                </li>
                <li>
                  <strong>Una exhaustiveness entre 8 y 16</strong> es un buen equilibrio para el docking.
                  Valores mayores mejoran la búsqueda, pero pueden tardar varios minutos.
                </li>
                <li>
                  <strong>Para validar el protocolo (redocking)</strong>, usa el ligando cristalográfico
                  como molécula de entrada Y como referencia de la caja. Un RMSD &lt; 2 Å entre la mejor
                  pose y la cristalográfica confirma que el protocolo funciona.
                </li>
              </ul>

              {/* Solo lo que un biólogo puede resolver desde la interfaz. Lo que
                  depende de cómo esté montada la plataforma es cosa del
                  administrador y aquí solo se dice que se le avise (principio 7). */}
              <h3>Errores frecuentes</h3>
              <div className="tutorial-errores">
                {ERRORES.map(e => (
                  <div key={e.titulo} className="tutorial-error">
                    <h4><Icono nombre="error" />{e.titulo}</h4>
                    <p>{e.texto}</p>
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
