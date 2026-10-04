import { useState } from 'react';
import '../styles/Tutorial.css';

const SECCIONES = [
  { id: 'plataforma', emoji: '🧬', titulo: 'Visión general' },
  { id: 'moleculas',  emoji: '🧪', titulo: 'Pestaña "Moléculas"' },
  { id: 'algoritmos', emoji: '📋', titulo: 'Pestaña "Algoritmos"' },
  { id: 'builder',    emoji: '🔧', titulo: 'Constructor Visual' },
  { id: 'nodos',      emoji: '📦', titulo: 'Tipos de nodo' },
  { id: 'flujo',      emoji: '▶️',  titulo: 'Flujo paso a paso' },
  { id: 'consejos',   emoji: '💡', titulo: 'Consejos y errores' },
];

const NodoEjemplo = ({ color, emoji, titulo, descripcion, entradas, salida }) => (
  <div className="tutorial-nodo-card">
    <div className="tutorial-nodo-header" style={{ background: color }}>
      {emoji} {titulo}
    </div>
    <div className="tutorial-nodo-body">
      <p>{descripcion}</p>
      {entradas && <p className="tutorial-nodo-meta"><strong>Entradas:</strong> {entradas}</p>}
      {salida   && <p className="tutorial-nodo-meta"><strong>Salida:</strong> {salida}</p>}
    </div>
  </div>
);

const PipelineDiagram = () => (
  <div className="pipeline-diagram">
    {[
      { emoji: '🧪', label: 'Subir molécula/BD',       color: '#2ecc71' },
      { emoji: '📤', label: 'Upload / Seleccionar',     color: '#3498db' },
      { emoji: '⚗️', label: 'Preprocesar',              color: '#e67e22' },
      { emoji: '📐', label: 'Alinear / Comparar',       color: '#27ae60' },
      { emoji: '🔬', label: 'Docking',                  color: '#8e44ad' },
      { emoji: '📥', label: 'Descargar resultados',     color: '#34495e' },
    ].map((paso, idx, arr) => (
      <div key={idx} className="pipeline-step-wrapper">
        <div className="pipeline-step" style={{ borderColor: paso.color }}>
          <span className="pipeline-step-emoji">{paso.emoji}</span>
          <span className="pipeline-step-label">{paso.label}</span>
        </div>
        {idx < arr.length - 1 && <div className="pipeline-arrow">→</div>}
      </div>
    ))}
  </div>
);

export default function Tutorial() {
  const [seccionAbierta, setSeccionAbierta] = useState('plataforma');

  return (
    <div className="tutorial-container">
      <div className="tutorial-hero">
        <h1 className="tutorial-hero-title">🧬 Guía de la Plataforma</h1>
        <p className="tutorial-hero-subtitle">
          Todo lo que necesitas para realizar cribado virtual de forma sencilla,
          aunque no tengas experiencia en programación.
        </p>
      </div>

      <div className="tutorial-layout">
        <nav className="tutorial-index">
          {SECCIONES.map(s => (
            <button
              key={s.id}
              className={`tutorial-index-btn ${seccionAbierta === s.id ? 'activo' : ''}`}
              onClick={() => setSeccionAbierta(s.id)}
            >
              {s.emoji} {s.titulo}
            </button>
          ))}
        </nav>

        <div className="tutorial-content">

          {/* ── 1. VISIÓN GENERAL ── */}
          {seccionAbierta === 'plataforma' && (
            <section className="tutorial-section">
              <h2>🧬 ¿Qué es esta plataforma?</h2>
              <p>
                Esta plataforma de <strong>cribado virtual</strong> te permite analizar moléculas y
                predecir cuáles podrían ser buenos fármacos — sin necesidad de escribir
                una sola línea de código. Funciona como una cinta de montaje visual: tú
                decides qué operaciones aplicar a tus moléculas y en qué orden, y la
                plataforma las ejecuta automáticamente en una cola de procesamiento.
              </p>

              <div className="tutorial-cards-grid">
                <div className="tutorial-info-card">
                  <h3>🧪 Moléculas</h3>
                  <p>Sube y gestiona tus moléculas individuales y bases de datos (SDF con múltiples moléculas).
                    Son la materia prima de todos los análisis.</p>
                </div>
                <div className="tutorial-info-card">
                  <h3>📋 Algoritmos</h3>
                  <p>Sube o gestiona los scripts científicos disponibles (conversión de formatos,
                    filtros de Lipinski, generación 3D, docking…).</p>
                </div>
                <div className="tutorial-info-card">
                  <h3>🔧 Constructor Visual</h3>
                  <p>Diseña visualmente tu pipeline arrastrando bloques y conectándolos.
                    La ejecución va a una cola para no bloquear a otros usuarios.</p>
                </div>
                <div className="tutorial-info-card">
                  <h3>📬 Resultados</h3>
                  <p>Encuentra los ficheros de tus workflows y cribados para descargarlos. Desde
                    aquí también puedes enviar una molécula directamente a un algoritmo concreto,
                    sin construir un pipeline completo.</p>
                </div>
              </div>

              <div className="tutorial-callout">
                <strong>Flujo habitual de trabajo:</strong>
                <PipelineDiagram />
              </div>

              <div className="tutorial-callout" style={{ background: '#e8f8f0', borderLeftColor: '#27ae60' }}>
                <strong>Cola de procesamiento:</strong> cuando varios usuarios ejecutan workflows
                a la vez, los trabajos se encolan y se procesan uno a uno. Al terminar, recibirás
                un <strong>correo electrónico</strong> con el resultado. No hace falta quedarse
                mirando la pantalla.
              </div>
            </section>
          )}

          {/* ── 2. MOLÉCULAS ── */}
          {seccionAbierta === 'moleculas' && (
            <section className="tutorial-section">
              <h2>🧪 Pestaña "Moléculas"</h2>
              <p>
                Antes de construir un pipeline en el Constructor Visual, debes tener tus moléculas
                disponibles en el servidor. Esta pestaña es el <strong>almacén central</strong>
                de todos los archivos moleculares de la plataforma.
              </p>

              <h3>Tipos de archivo que puedes subir</h3>
              <div className="tutorial-table-wrapper">
                <table className="tutorial-table">
                  <thead>
                    <tr><th>Tipo</th><th>Formatos</th><th>¿Para qué?</th></tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td><span className="badge" style={{ background: '#3498db' }}>Molécula individual</span></td>
                      <td><code>.mol2</code>, <code>.sdf</code>, <code>.pdb</code>, <code>.pdbqt</code></td>
                      <td>Ligandos, receptores, referencias cristalográficas</td>
                    </tr>
                    <tr>
                      <td><span className="badge" style={{ background: '#8e44ad' }}>Base de datos</span></td>
                      <td><code>.sdf</code> multi-molécula</td>
                      <td>Librerías de compuestos para cribado masivo</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <h3>¿Cómo subir un archivo?</h3>
              <ol className="tutorial-steps">
                <li>Ve a la pestaña <strong>🧪 Moléculas</strong> en la barra de navegación.</li>
                <li>Elige el formulario adecuado: <em>"Molécula individual"</em> o <em>"Base de datos"</em>.</li>
                <li>Arrastra el archivo a la zona punteada, o haz clic en ella para buscarlo en tu ordenador.</li>
                <li>Pulsa <strong>"Subir"</strong>. El archivo aparecerá en la biblioteca inferior en segundos.</li>
              </ol>

              <h3>La biblioteca de archivos</h3>
              <p>
                Bajo los formularios encontrarás dos columnas: <strong>Moléculas</strong> (archivos
                individuales o SDF pequeños) y <strong>Bases de datos</strong> (SDF con más de 10 KB,
                que suelen contener decenas o cientos de moléculas). Cada archivo tiene botones
                para descargarlo o eliminarlo.
              </p>

              <div className="tutorial-callout">
                💡 El número de moléculas que contiene cada SDF se calcula automáticamente al subir
                el archivo y se muestra junto al nombre. Un SDF con 1 molécula aparece como molécula
                individual; uno con muchas, como base de datos.
              </div>

              <h3>¿Cómo se usan en el Builder?</h3>
              <p>
                Una vez subidos, los archivos están disponibles de forma inmediata en los nodos
                del Constructor Visual: el nodo <strong>Seleccionar Molécula</strong> lista todas las
                moléculas, y el nodo <strong>Seleccionar BD</strong> lista todas las bases de datos
                en formato SDF. No hay que volver a subir nada.
              </p>
            </section>
          )}

          {/* ── 3. ALGORITMOS ── */}
          {seccionAbierta === 'algoritmos' && (
            <section className="tutorial-section">
              <h2>📋 Pestaña "Algoritmos"</h2>
              <p>
                Aquí se gestionan los <strong>scripts científicos</strong> que la plataforma puede
                ejecutar. Cada algoritmo es un archivo Python (<code>.py</code>) con una etiqueta
                especial que le indica al sistema qué tipo de operación realiza.
              </p>

              <h3>Tipos de algoritmo</h3>
              <div className="tutorial-table-wrapper">
                <table className="tutorial-table">
                  <thead>
                    <tr><th>Tipo</th><th>¿Qué hace?</th><th>Ejemplos disponibles</th></tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td><span className="badge" style={{ background: '#e67e22' }}>preprocesado</span></td>
                      <td>Prepara o filtra una molécula</td>
                      <td>preparacionObabel, filtroLipinski, filtroObabel, gen3dRDKit, limpiezaSDF</td>
                    </tr>
                    <tr>
                      <td><span className="badge" style={{ background: '#2ecc71' }}>alineacion</span></td>
                      <td>Alinea o reorienta una o dos moléculas</td>
                      <td>alinear3D (O3A), alinearMCS, centerMol</td>
                    </tr>
                    <tr>
                      <td><span className="badge" style={{ background: '#f39c12' }}>comparacion</span></td>
                      <td>Compara dos moléculas y da un valor numérico</td>
                      <td>similaridadTanimoto, rmsdConformaciones</td>
                    </tr>
                    <tr>
                      <td><span className="badge" style={{ background: '#8e44ad' }}>docking</span></td>
                      <td>Acopla un ligando en un receptor proteico</td>
                      <td>dockingSmina</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <h3>¿Cómo subir un algoritmo?</h3>
              <ol className="tutorial-steps">
                <li>Haz clic en <strong>"Subir nuevo algoritmo"</strong>.</li>
                <li>Rellena el nombre y la descripción.</li>
                <li>Selecciona el tipo correcto: preprocesado, alineacion, comparacion o docking.</li>
                <li>Elige el archivo <code>.py</code> desde tu ordenador.</li>
                <li>El sistema ejecutará el script sobre moléculas de referencia, invocándolo
                  como corresponde al tipo elegido, antes de aceptarlo en el catálogo.</li>
                <li>Si todo es correcto, el algoritmo aparecerá en el listado y estará disponible
                  en el Constructor Visual.</li>
              </ol>

              <div className="tutorial-callout warning">
                ⚠️ Si el script falla, no escribe el resultado en el último argumento, o no
                termina con código 0, la subida se rechazará con el motivo y la salida del script.
              </div>
            </section>
          )}

          {/* ── 4. CONSTRUCTOR VISUAL ── */}
          {seccionAbierta === 'builder' && (
            <section className="tutorial-section">
              <h2>🔧 ¿Qué es el Constructor Visual?</h2>
              <p>
                Es el <strong>editor visual de pipelines</strong>. En lugar de ejecutar scripts
                manualmente uno a uno, aquí construyes un flujo de trabajo completo de forma
                gráfica, conectando bloques (nodos) entre sí.
              </p>

              <h3>Las tres zonas de la pantalla</h3>
              <div className="tutorial-zonas">
                <div className="zona-card">
                  <div className="zona-header">⬅️ Panel izquierdo — Paleta</div>
                  <p>Lista de todos los tipos de nodo. <strong>Arrástralos</strong> al canvas central para añadirlos.</p>
                </div>
                <div className="zona-card">
                  <div className="zona-header">🖥️ Centro — Canvas</div>
                  <p>El lienzo donde construyes el pipeline. Coloca, configura y conecta nodos con flechas.</p>
                </div>
                <div className="zona-card">
                  <div className="zona-header">➡️ Panel derecho — Resultados</div>
                  <p>Aparece tras ejecutar. Muestra el estado de cada nodo, errores y enlaces de descarga.</p>
                </div>
              </div>

              <h3>Barra de herramientas (arriba)</h3>
              <div className="tutorial-table-wrapper">
                <table className="tutorial-table">
                  <thead>
                    <tr><th>Botón / Control</th><th>¿Qué hace?</th></tr>
                  </thead>
                  <tbody>
                    <tr><td>➕ Nuevo Workflow</td><td>Crea un workflow vacío con un nombre que tú eliges.</td></tr>
                    <tr><td>💾 Guardar</td><td>Guarda el diseño actual en la base de datos.</td></tr>
                    <tr><td>🗑️ Limpiar</td><td>Borra todos los nodos del canvas (sin eliminar el workflow guardado).</td></tr>
                    <tr><td>Selector desplegable</td><td>Carga un workflow guardado anteriormente.</td></tr>
                    <tr>
                      <td>▶️ Ejecutar Workflow</td>
                      <td>
                        Guarda el canvas automáticamente, encola el trabajo en Celery y muestra el progreso:
                        <br/><em>⏳ En cola… → ⚙️ Procesando… → Resultados</em>
                        <br/>Al terminar recibirás un correo electrónico con el resultado.
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div className="tutorial-callout" style={{ background: '#e8f8f0', borderLeftColor: '#27ae60' }}>
                <strong>Auto-guardado:</strong> al pulsar "Ejecutar Workflow", el canvas se guarda
                automáticamente antes de encolar el trabajo. Si el workflow no existe todavía,
                te pedirá un nombre y lo creará solo.
              </div>

              <h3>¿Cómo eliminar un nodo individual?</h3>
              <p>
                Cada nodo tiene un botón <strong>×</strong> en la esquina superior derecha de su
                cabecera. Haz clic en él para eliminar solo ese nodo (y sus conexiones) sin
                borrar el resto del canvas.
              </p>

              <h3>¿Cómo conectar dos nodos?</h3>
              <ol className="tutorial-steps">
                <li>Pasa el ratón por encima del borde <strong>derecho</strong> de un nodo hasta
                  que aparezca un círculo (puerto de salida).</li>
                <li>Haz <strong>clic y arrastra</strong> desde ese círculo.</li>
                <li>Suéltalo sobre el círculo del borde <strong>izquierdo</strong> del nodo
                  siguiente (puerto de entrada).</li>
                <li>Aparecerá una línea que los une.</li>
              </ol>
              <div className="tutorial-callout">
                💡 Puedes hacer zoom con la rueda del ratón y mover el canvas arrastrando el fondo.
                El minimapa (esquina inferior derecha) te ayuda a orientarte en workflows grandes.
              </div>

              <h3>Los nodos cargan datos del servidor</h3>
              <p>
                Los nodos de tipo <strong>Preprocesar</strong>, <strong>Alinear</strong>,
                <strong> Comparar</strong> y <strong>Docking</strong> cargan automáticamente los
                algoritmos subidos en la pestaña "Algoritmos". El nodo <strong>Seleccionar
                Molécula</strong> muestra los archivos de la pestaña "Moléculas" y el nodo
                <strong> Seleccionar BD</strong> muestra las bases de datos SDF disponibles.
                Pulsa <em>"actualizar"</em> dentro del nodo si acabas de subir algo nuevo.
              </p>
            </section>
          )}

          {/* ── 5. TIPOS DE NODO ── */}
          {seccionAbierta === 'nodos' && (
            <section className="tutorial-section">
              <h2>📦 Tipos de nodo y sus funciones</h2>
              <p>Cada nodo realiza una operación distinta. Todos tienen un botón <strong>×</strong> para eliminarse individualmente.</p>

              <div className="tutorial-nodos-grid">
                <NodoEjemplo
                  color="linear-gradient(135deg,#3498db,#2980b9)"
                  emoji="📤" titulo="Upload Molécula"
                  descripcion="Sube un archivo de molécula desde tu ordenador (.sdf, .mol2, .pdb…). Es el punto de entrada cuando quieres analizar un archivo nuevo que aún no está en el servidor."
                  salida="Archivo de molécula disponible para el siguiente nodo"
                />
                <NodoEjemplo
                  color="linear-gradient(135deg,#9b59b6,#8e44ad)"
                  emoji="📂" titulo="Seleccionar BD"
                  descripcion="Muestra las bases de datos SDF subidas en la pestaña Moléculas. Selecciona la que quieres usar en el pipeline. Pulsa 'actualizar' si acabas de subir una nueva base de datos."
                  salida="Ruta al SDF de la base de datos en el servidor"
                />
                <NodoEjemplo
                  color="linear-gradient(135deg,#e74c3c,#c0392b)"
                  emoji="🧬" titulo="Seleccionar Molécula"
                  descripcion="Escoge una molécula ya disponible en el servidor (subida desde la pestaña Moléculas). Útil para reutilizar archivos sin volver a subirlos."
                  salida="Ruta al archivo de molécula en el servidor"
                />
                <NodoEjemplo
                  color="linear-gradient(135deg,#e67e22,#d35400)"
                  emoji="⚗️" titulo="Preprocesar"
                  descripcion="Aplica una operación de preparación: conversión de formato, añadir hidrógenos a pH 7.4, generar coordenadas 3D, centrar, filtrar por propiedades (Lipinski, OpenBabel --filter), o limpiar un SDF multi-molécula."
                  entradas="Molécula (izquierda)"
                  salida="Molécula procesada o JSON con resultados (derecha)"
                />
                <NodoEjemplo
                  color="linear-gradient(135deg,#2ecc71,#27ae60)"
                  emoji="📐" titulo="Alinear"
                  descripcion="Alinea una molécula sobre una referencia en 3D. Opciones: Open3DAlign (O3A) para alineación global, MCS para alinear por subestructura común, o centrado PCA."
                  entradas="Molécula query (puerto izq.) + Referencia opcional (puerto izq. superior)"
                  salida="Molécula alineada en SDF"
                />
                <NodoEjemplo
                  color="linear-gradient(135deg,#f39c12,#e67e22)"
                  emoji="⚖️" titulo="Comparar"
                  descripcion="Compara dos moléculas y devuelve un valor numérico: similitud Tanimoto (0–1) mediante fingerprints de Morgan, o RMSD en Ångströms entre dos poses de la misma molécula."
                  entradas="Molécula 1 (puerto mol1 — izquierda) + Molécula 2 (puerto mol2 — abajo)"
                  salida="JSON con el valor numérico"
                />
                <NodoEjemplo
                  color="linear-gradient(135deg,#8e44ad,#6c3483)"
                  emoji="🔬" titulo="Docking"
                  descripcion="Acopla el ligando en el sitio de unión del receptor proteico usando Smina. Configura la función de scoring, el modo de caja (automática sobre ligando, sobre referencia, o manual) y la exhaustiveness."
                  entradas="Ligando (izq.) + Receptor PDBQT (abajo) + Referencia opcional (arriba)"
                  salida="SDF con todas las poses + JSON con energías de afinidad"
                />
                <NodoEjemplo
                  color="linear-gradient(135deg,#1abc9c,#16a085)"
                  emoji="▶️" titulo="Ejecutar"
                  descripcion="Marca el inicio del pipeline. Conéctalo al primer nodo de datos para indicar que el workflow está listo para correr. No realiza ninguna operación por sí solo."
                  entradas="—"
                  salida="Señal de inicio hacia el siguiente nodo"
                />
                <NodoEjemplo
                  color="linear-gradient(135deg,#34495e,#2c3e50)"
                  emoji="📥" titulo="Descargar"
                  descripcion="Marca un archivo como descargable. Tras la ejecución aparecerá un enlace en el panel de resultados para guardar el archivo en tu ordenador."
                  entradas="Archivo de cualquier nodo anterior"
                  salida="Enlace de descarga en el panel de resultados"
                />
              </div>
            </section>
          )}

          {/* ── 6. FLUJO COMPLETO ── */}
          {seccionAbierta === 'flujo' && (
            <section className="tutorial-section">
              <h2>▶️ Ejemplo completo: comparar dos moléculas</h2>
              <p>
                Vamos a calcular la similitud Tanimoto entre dos moléculas disponibles en el servidor.
                Antes de empezar, asegúrate de haber subido los archivos en la pestaña <strong>🧪 Moléculas</strong>.
              </p>

              <div className="tutorial-steps-visual">
                {[
                  {
                    n: 1,
                    titulo: 'Sube tus moléculas (pestaña Moléculas)',
                    detalle: 'Ve a 🧪 Moléculas y sube los dos archivos .mol2 o .sdf que quieres comparar. Aparecerán en la biblioteca. Solo tienes que hacerlo una vez; estarán disponibles en todos los workflows.',
                  },
                  {
                    n: 2,
                    titulo: 'Crea el workflow en el Constructor Visual',
                    detalle: 'Ve a 🔧 Constructor Visual y pulsa "➕ Nuevo Workflow". Escribe un nombre descriptivo (p. ej. "Comparación Tanimoto") y pulsa Aceptar.',
                  },
                  {
                    n: 3,
                    titulo: 'Añade el nodo Ejecutar',
                    detalle: 'Arrastra el nodo "Ejecutar" al canvas. Este nodo marca el inicio del pipeline.',
                  },
                  {
                    n: 4,
                    titulo: 'Añade dos nodos "Seleccionar Molécula"',
                    detalle: 'Arrastra dos nodos "Seleccionar Molécula". En el desplegable de cada uno elige una de las moléculas subidas. Si no aparecen, pulsa "actualizar" dentro del nodo.',
                  },
                  {
                    n: 5,
                    titulo: 'Conecta los nodos al nodo Ejecutar',
                    detalle: 'Arrastra desde el puerto derecho (salida) del nodo Ejecutar hacia el puerto izquierdo de cada Seleccionar Molécula.',
                  },
                  {
                    n: 6,
                    titulo: 'Añade un nodo Comparar',
                    detalle: 'Arrastra "Comparar" al canvas. En el desplegable elige "similaridadTanimoto". Conecta el primer Seleccionar Molécula al puerto mol1 (izquierda del Comparar) y el segundo al puerto mol2 (abajo del Comparar).',
                  },
                  {
                    n: 7,
                    titulo: 'Añade un nodo Descargar',
                    detalle: 'Conecta la salida del nodo Comparar al nodo Descargar. Esto hará que el JSON con el resultado aparezca como enlace de descarga.',
                  },
                  {
                    n: 8,
                    titulo: 'Ejecuta el workflow',
                    detalle: 'Pulsa "▶️ Ejecutar Workflow". El botón mostrará "⏳ En cola…" mientras espera al worker y "⚙️ Procesando…" mientras corre. Al terminar aparecerá el panel de resultados con el JSON de similitud y el enlace de descarga. Además recibirás un correo de confirmación.',
                  },
                ].map(paso => (
                  <div key={paso.n} className="tutorial-step-visual">
                    <div className="tutorial-step-number">{paso.n}</div>
                    <div className="tutorial-step-content">
                      <h4>{paso.titulo}</h4>
                      <p>{paso.detalle}</p>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* ── 7. CONSEJOS ── */}
          {seccionAbierta === 'consejos' && (
            <section className="tutorial-section">
              <h2>💡 Consejos y errores frecuentes</h2>

              <h3>Consejos</h3>
              <ul className="tutorial-tips">
                <li>
                  <strong>Sube tus moléculas antes de abrir el Builder.</strong> Los nodos
                  "Seleccionar Molécula" y "Seleccionar BD" cargan la lista al abrirse. Si subes
                  un archivo después, pulsa el enlace <em>"actualizar"</em> dentro del nodo.
                </li>
                <li>
                  <strong>El botón Ejecutar guarda automáticamente.</strong> Ya no tienes que
                  pulsar "Guardar" antes de ejecutar — el sistema lo hace por ti. Aun así,
                  puedes guardar manualmente en cualquier momento para no perder el diseño.
                </li>
                <li>
                  <strong>No cierres la pestaña mientras ves "En cola…".</strong> Aunque el
                  trabajo se procesa en el servidor (puedes cerrar y volver), si cierras el
                  navegador perderás la notificación visual. El correo electrónico llegará
                  igualmente al terminar.
                </li>
                <li>
                  <strong>Comprueba el Lipinski antes del docking.</strong> Si la molécula
                  falla el filtro Lipinski (FAIL), el docking consumirá tiempo con un compuesto
                  que probablemente no sea drug-like.
                </li>
                <li>
                  <strong>El receptor debe estar en PDBQT.</strong> Smina solo acepta receptores
                  en formato PDBQT. Prepáralo externamente con AutoDockTools o MGLTools
                  antes de subirlo.
                </li>
                <li>
                  <strong>exhaustiveness entre 8 y 16</strong> es un buen equilibrio para docking.
                  Valores mayores mejoran la búsqueda pero pueden tardar varios minutos.
                </li>
                <li>
                  <strong>Para validar el protocolo (redocking)</strong>, usa el mismo ligando
                  cristalográfico como query Y como referencia de caja. Un RMSD &lt; 2 Å
                  entre la mejor pose y la cristalográfica confirma que el protocolo funciona.
                </li>
              </ul>

              <h3>Errores frecuentes</h3>
              <div className="tutorial-errores">
                <div className="tutorial-error-card">
                  <div className="error-titulo">❌ "Sin bases de datos disponibles" en el nodo Seleccionar BD</div>
                  <p>No hay archivos SDF subidos en la pestaña Moléculas. Ve a 🧪 Moléculas, sube un SDF
                    y vuelve al Builder. Pulsa "actualizar" dentro del nodo para refrescar la lista.</p>
                </div>
                <div className="tutorial-error-card">
                  <div className="error-titulo">❌ "Nodo sin entrada de molécula"</div>
                  <p>El nodo de preprocesado/alineación no tiene ninguna conexión en su puerto izquierdo.
                    Conecta la salida del nodo anterior a este.</p>
                </div>
                <div className="tutorial-error-card">
                  <div className="error-titulo">❌ "Algoritmo no encontrado"</div>
                  <p>El script seleccionado no existe en la carpeta <code>algoritmos/</code> del servidor
                    o no ha sido subido en la pestaña "Algoritmos". Comprueba que el tipo del nodo
                    coincide con el tipo del algoritmo.</p>
                </div>
                <div className="tutorial-error-card">
                  <div className="error-titulo">❌ El botón se queda en "⏳ En cola…" indefinidamente</div>
                  <p>El worker de Celery no está corriendo o no está conectado a Redis. Contacta con
                    el administrador del servidor. En local, lanza el worker con
                    <code> celery -A app.celery_app worker --loglevel=info -P solo</code>.</p>
                </div>
                <div className="tutorial-error-card">
                  <div className="error-titulo">❌ "OpenBabel no está instalado"</div>
                  <p>El comando <code>obabel</code> no está disponible en el servidor. Instálalo con
                    <code> conda install -c conda-forge openbabel</code>.</p>
                </div>
                <div className="tutorial-error-card">
                  <div className="error-titulo">❌ "Smina no está instalado"</div>
                  <p>Instala con <code>conda install -c conda-forge smina</code> o descarga el binario
                    de GitHub y añádelo al PATH del servidor.</p>
                </div>
                <div className="tutorial-error-card">
                  <div className="error-titulo">❌ El workflow termina pero no hay archivos descargables</div>
                  <p>Asegúrate de añadir un nodo <strong>Descargar</strong> conectado a la salida que
                    quieres guardar. Sin ese nodo, el archivo se genera internamente pero no aparece
                    en el panel de resultados.</p>
                </div>
              </div>
            </section>
          )}

        </div>
      </div>
    </div>
  );
}
