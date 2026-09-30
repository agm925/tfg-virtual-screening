import React, { useState, useCallback, useEffect } from 'react';
import ReactFlow, {
  addEdge,
  useNodesState,
  useEdgesState,
  Background,
  Controls,
  MiniMap,
} from 'reactflow';
import 'reactflow/dist/style.css';
import '../styles/visualBuilder.css';

// Componentes de nodos personalizados
import UploadNodoNode from './nodos/UploadNodoNode';
import AlgoritmoNodoNode from './nodos/AlgoritmoNodoNode';
import ComparacionNodoNode from './nodos/ComparacionNodoNode';
import PreprocesadoNodoNode from './nodos/PreprocesadoNodoNode';
import DockingNodoNode from './nodos/DockingNodoNode';
import EjecutarNodoNode from './nodos/EjecutarNodoNode';
import DescargarNodoNode from './nodos/DescargarNodoNode';
import SelectDBNodoNode from './nodos/SelectDBNodoNode';
import SelectMolNodoNode from './nodos/SelectMolNodoNode';

// Hook personalizado para llamadas API
import useWorkflowAPI from '../hooks/useWorkflowAPI';
import MolViewer3D from './MolViewer3D';

const nodeTypes = {
  upload:       UploadNodoNode,
  alineacion:   AlgoritmoNodoNode,
  comparacion:  ComparacionNodoNode,
  preprocesado: PreprocesadoNodoNode,
  docking:      DockingNodoNode,
  ejecutar:     EjecutarNodoNode,
  descargar:    DescargarNodoNode,
  selectDB:     SelectDBNodoNode,
  selectMol:    SelectMolNodoNode,
};

const VisualBuilder = ({ usuario }) => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [workflows, setWorkflows] = useState([]);
  const [workflowActual, setWorkflowActual] = useState(null);
  const [resultsPanel, setResultsPanel] = useState(null);
  const [ejecutando,       setEjecutando]       = useState(false);
  const [estadoEjecucion,  setEstadoEjecucion]  = useState(null); // 'pendiente'|'procesando'|null
  const [batchProgreso,    setBatchProgreso]     = useState(null); // { actual, total, molecula_actual }
  const [visor3D,          setVisor3D]          = useState(null); // archivo a visualizar
  const [nodoId, setNodoId] = useState(0);

  const {
    crearWorkflow,
    actualizarWorkflow,
    obtenerWorkflows,
    ejecutarWorkflow,
    esperarEjecucion,
    descargarResultado
  } = useWorkflowAPI();

  // Cargar workflows guardados al inicio
  useEffect(() => {
    if (usuario?.id) {
      cargarWorkflows();
    }
  }, [usuario]);

  const cargarWorkflows = async () => {
    try {
      const data = await obtenerWorkflows(usuario.id);
      setWorkflows(data);
    } catch (err) {
      console.error("Error cargando workflows:", err);
    }
  };

  const onConnect = useCallback(
    (connection) => setEdges((eds) => addEdge(connection, eds)),
    [setEdges]
  );

  // ===== PALETA DE NODOS =====
  const tiposNodos = [
    { tipo: 'upload',       label: '📤 Upload Molécula',    color: '#3498db' },
    { tipo: 'selectDB',     label: '📂 Seleccionar BD',     color: '#9b59b6' },
    { tipo: 'selectMol',    label: '🧬 Seleccionar Molécula', color: '#e74c3c' },
    { tipo: 'preprocesado', label: '⚗️ Preprocesar',        color: '#e67e22' },
    { tipo: 'alineacion',   label: '📐 Alinear',            color: '#2ecc71' },
    { tipo: 'comparacion',  label: '⚖️ Comparar',           color: '#f39c12' },
    { tipo: 'docking',      label: '🔬 Docking',            color: '#8e44ad' },
    { tipo: 'ejecutar',     label: '▶️ Ejecutar',           color: '#1abc9c' },
    { tipo: 'descargar',    label: '📥 Descargar',          color: '#34495e' },
  ];

  // Drag-drop de nodos desde la paleta
  const onDragStart = (event, tipo) => {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('tipo', tipo);
  };

  const onDragOver = (event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  };

  const onDrop = (event) => {
    event.preventDefault();
    const tipo = event.dataTransfer.getData('tipo');
    
    const reactFlowBounds = document.querySelector('.react-flow-wrapper').getBoundingClientRect();
    const position = {
      x: event.clientX - reactFlowBounds.left,
      y: event.clientY - reactFlowBounds.top,
    };

    const nuevoNodo = {
      id: `${tipo}_${nodoId}`,
      type: tipo,
      position,
      data: { label: tiposNodos.find(n => n.tipo === tipo)?.label || tipo },
    };

    setNodes((nds) => [...nds, nuevoNodo]);
    setNodoId(nodoId + 1);
  };

  // Crear nuevo workflow
  const crearNuevo = async () => {
    const nombre = prompt("Nombre del workflow:");
    if (!nombre) return;

    try {
      const nuevoWf = await crearWorkflow({
        nombre,
        descripcion: "Workflow visual",
        grafo_json: { nodes: [], edges: [] },
      });

      setWorkflowActual(nuevoWf);
      setNodes([]);
      setEdges([]);
      setResultsPanel(null);
      cargarWorkflows();
    } catch (err) {
      alert("Error creando workflow: " + err.message);
    }
  };

  // Guardar workflow actual
  const guardarWorkflow = async () => {
    if (!workflowActual) {
      alert("No hay workflow para guardar");
      return;
    }

    try {
      const grafo = { nodes, edges };
      await actualizarWorkflow(workflowActual.id, {
        nombre: workflowActual.nombre,
        descripcion: workflowActual.descripcion,
        grafo_json: grafo,
      });
      alert("Workflow guardado correctamente");
      cargarWorkflows();
    } catch (err) {
      alert("Error guardando workflow: " + err.message);
    }
  };

  // Cargar workflow guardado
  // React Flow exige que TODO nodo traiga `position: {x, y}`; si falta, revienta
  // con "Cannot read properties of undefined (reading 'x')" y se lleva por
  // delante la página entera: pantalla en blanco, sin mensaje. Y el grafo puede
  // venir sin ella perfectamente, porque la API lo acepta y el motor lo ejecuta
  // igual (la posición es cosa del lienzo, no del cálculo). Se colocan en
  // cascada los que no la traigan, que es mejor que no poder abrir el flujo.
  const conPosicion = (nodos) =>
    (nodos || []).map((nodo, i) => (
      nodo && typeof nodo.position?.x === 'number' && typeof nodo.position?.y === 'number'
        ? nodo
        : { ...nodo, position: { x: 80 + (i % 4) * 260, y: 80 + Math.floor(i / 4) * 170 } }
    ));

  const cargarWorkflow = (workflow) => {
    setWorkflowActual(workflow);
    const grafo = workflow.grafo_json || { nodes: [], edges: [] };
    setNodes(conPosicion(grafo.nodes));
    setEdges(grafo.edges || []);
    setResultsPanel(null);
  };

  // Ejecutar workflow — encola en Celery y hace polling hasta que termina
  const ejecutar = async () => {
    if (nodes.length === 0) {
      alert("Añade nodos al canvas antes de ejecutar");
      return;
    }

    setEjecutando(true);
    setEstadoEjecucion('pendiente');
    setResultsPanel(null);
    setBatchProgreso(null);
    try {
      // Auto-crear workflow si no existe
      let wf = workflowActual;
      if (!wf) {
        const nombre = prompt("Nombre del workflow (se creará automáticamente):") || "Workflow sin nombre";
        wf = await crearWorkflow({
          nombre,
          descripcion: "Workflow visual",
          grafo_json: { nodes: [], edges: [] },
        });
        setWorkflowActual(wf);
        cargarWorkflows();
      }

      // Guardar canvas antes de encolar
      await actualizarWorkflow(wf.id, {
        nombre: wf.nombre,
        descripcion: wf.descripcion,
        grafo_json: { nodes, edges },
      });

      // Encolar tarea Celery → devuelve { ejecucion_id } inmediatamente
      const { ejecucion_id } = await ejecutarWorkflow(wf.id);

      // Polling cada 3 s hasta que el worker termine
      const resultado = await esperarEjecucion(ejecucion_id, (datos) => {
        setEstadoEjecucion(datos.estado);
        const rj = datos.resultados_json;
        if (rj && rj.modo === 'batch' && rj.total > 0) {
          setBatchProgreso({ actual: rj.progreso, total: rj.total, molecula: rj.molecula_actual });
        }
      });

      setResultsPanel(resultado);

      // Marcar visualmente los nodos
      if (resultado?.resultados) {
        setNodes((nds) =>
          nds.map((node) => ({
            ...node,
            data: {
              ...node.data,
              ejecutado: !!resultado.resultados[node.id],
              error: resultado.resultados[node.id]?.estado === 'error',
            },
          }))
        );
      }
    } catch (err) {
      alert("Error ejecutando workflow: " + err.message);
    } finally {
      setEjecutando(false);
      setEstadoEjecucion(null);
      setBatchProgreso(null);
    }
  };

  // Limpiar canvas
  const limpiar = () => {
    if (window.confirm("¿Limpiar todos los nodos?")) {
      setNodes([]);
      setEdges([]);
      setWorkflowActual(null);
      setResultsPanel(null);
    }
  };

  // Normaliza el score a 0-100 para la barra visual
  const normalizarScore = (score, ranking, tipoScore) => {
    if (score == null) return 0;
    const scores = ranking.filter(r => r.score != null).map(r => r.score);
    if (scores.length === 0) return 0;
    const min = Math.min(...scores);
    const max = Math.max(...scores);
    if (max === min) return 50;
    if (tipoScore === 'similitud') return ((score - min) / (max - min)) * 100;
    return ((max - score) / (max - min)) * 100; // invertido: menor es mejor
  };

  const colorScore = (pct) => {
    const h = Math.round(pct * 1.2); // 0→rojo, 120→verde
    return `hsl(${h}, 70%, 45%)`;
  };

  return (
    <div className="visual-container">
      {visor3D && <MolViewer3D archivo={visor3D} onClose={() => setVisor3D(null)} />}
      {/* BARRA SUPERIOR */}
      <div className="visual-toolbar">
        <div className="toolbar-left">
          <button onClick={crearNuevo} className="btn btn-primary">
            ➕ Nuevo Workflow
          </button>
          <button onClick={guardarWorkflow} className="btn btn-secondary" disabled={!workflowActual}>
            💾 Guardar
          </button>
          <button onClick={limpiar} className="btn btn-danger">
            🗑️ Limpiar
          </button>
        </div>

        <div className="toolbar-center">
          <select onChange={(e) => cargarWorkflow(workflows[e.target.value])} className="workflow-select">
            <option value="">Cargar workflow...</option>
            {workflows.map((wf, idx) => (
              <option key={wf.id} value={idx}>
                {wf.nombre}
              </option>
            ))}
          </select>
        </div>

        <div className="toolbar-right">
          <button
            onClick={ejecutar}
            className="btn btn-success"
            disabled={ejecutando || nodes.length === 0}
          >
            {!ejecutando && '▶️ Ejecutar Workflow'}
            {ejecutando && estadoEjecucion === 'pendiente'  && '⏳ En cola…'}
            {ejecutando && estadoEjecucion === 'procesando' && batchProgreso
              && `⚙️ ${batchProgreso.actual}/${batchProgreso.total} moléculas…`}
            {ejecutando && estadoEjecucion === 'procesando' && !batchProgreso && '⚙️ Procesando…'}
            {ejecutando && !estadoEjecucion                 && '⏳ Encolando…'}
          </button>
        </div>
      </div>

      <div className="visual-content">
        {/* PALETA DE NODOS (Izquierda) */}
        <div className="visual-sidebar-left">
          <h3>Nodos Disponibles</h3>
          <div className="paleta-nodos">
            {tiposNodos.map((nodo) => (
              <div
                key={nodo.tipo}
                draggable
                onDragStart={(e) => onDragStart(e, nodo.tipo)}
                className="nodo-paleta"
                style={{ borderLeftColor: nodo.color }}
              >
                {nodo.label}
              </div>
            ))}
          </div>
          <p className="hint">Arrastra nodos al canvas</p>
        </div>

        {/* CANVAS REACT FLOW (Centro) */}
        <div className="visual-canvas-wrapper react-flow-wrapper" onDragOver={onDragOver} onDrop={onDrop}>
          {workflowActual && <h2 className="workflow-title">{workflowActual.nombre}</h2>}
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            fitView
          >
            <Background />
            <Controls />
            <MiniMap />
          </ReactFlow>
        </div>

        {/* PANEL DE RESULTADOS (Derecha) */}
        <div className="visual-sidebar-right">
          <h3>📊 Resultados</h3>

          {/* Progreso batch en tiempo real */}
          {ejecutando && batchProgreso && (
            <div className="batch-progress">
              <p className="batch-progress-label">
                ⚙️ Procesando molécula <strong>{batchProgreso.actual}</strong> de <strong>{batchProgreso.total}</strong>
              </p>
              <div className="batch-progress-bar">
                <div
                  className="batch-progress-fill"
                  style={{ width: `${Math.round(batchProgreso.actual / batchProgreso.total * 100)}%` }}
                />
              </div>
              {batchProgreso.molecula && (
                <p className="batch-progress-mol">{batchProgreso.molecula}</p>
              )}
            </div>
          )}

          {resultsPanel ? (
            <div className="results-panel">

              {/* ── Modo batch ── */}
              {resultsPanel.modo === 'batch' ? (
                <div className="batch-results">
                  <div className="batch-summary">
                    <span className="batch-stat ok">✅ {resultsPanel.total_exito} procesadas</span>
                    {resultsPanel.total_error > 0 && (
                      <span className="batch-stat err">❌ {resultsPanel.total_error} errores</span>
                    )}
                    {/* Registros del SDF que RDKit no pudo leer, y que por
                        tanto NO se han cribado. Se enseña aunque sea una
                        mala noticia: antes desaparecían sin dejar rastro y el
                        panel decía "N procesadas, 0 errores" sobre una
                        biblioteca de la que faltaba la mitad. */}
                    {resultsPanel.moleculas_descartadas > 0 && (
                      <span
                        className="batch-stat err"
                        title={`El fichero tiene ${resultsPanel.registros_en_fichero} registros, pero ${resultsPanel.moleculas_descartadas} no se pudieron leer y han quedado fuera del cribado`}
                      >
                        ⚠️ {resultsPanel.moleculas_descartadas} sin leer
                      </span>
                    )}
                    <span className="batch-stat bd">📂 {resultsPanel.base_de_datos}</span>
                  </div>

                  {/* Un cribado que transforma o filtra moléculas no tiene
                      ranking: su resultado son las moléculas. Ordenar por peso
                      molecular un filtro de Lipinski no dice nada. */}
                  {resultsPanel.modo_resultado === 'transformacion' && (
                    <div className="batch-summary">
                      <span className="batch-stat ok">
                        🧪 {resultsPanel.total_en_fichero ?? 0} moléculas en el fichero
                      </span>
                      {resultsPanel.no_cumplen > 0 && (
                        <span className="batch-stat err">🚫 {resultsPanel.no_cumplen} no cumplen el filtro</span>
                      )}
                    </div>
                  )}

                  {resultsPanel.moleculas_resultado && (
                    <button
                      onClick={() => descargarResultado(resultsPanel.moleculas_resultado)}
                      className="btn-csv-download"
                      title="Las moléculas resultantes, con las propiedades calculadas como campos del SDF"
                    >
                      📥 Descargar moléculas ({resultsPanel.moleculas_resultado.split('.').pop().toUpperCase()})
                    </button>
                  )}

                  {resultsPanel.csv_propiedades && (
                    <button
                      onClick={() => descargarResultado(resultsPanel.csv_propiedades)}
                      className="btn-csv-download"
                    >
                      📥 Descargar propiedades CSV
                    </button>
                  )}

                  {resultsPanel.csv_ranking && (
                    <button
                      onClick={() => descargarResultado(resultsPanel.csv_ranking)}
                      className="btn-csv-download"
                    >
                      📥 Descargar ranking CSV
                    </button>
                  )}

                  {resultsPanel.sdf_poses && (
                    <button
                      onClick={() => descargarResultado(resultsPanel.sdf_poses)}
                      className="btn-csv-download"
                      title="La mejor pose de cada molécula, en el orden del ranking"
                    >
                      📥 Descargar poses SDF
                    </button>
                  )}

                  {/* El CSV es el ranking: posicion, nombre y score. Este JSON
                      lleva TODAS las moleculas con los numeros de cada nodo
                      --MW, LogP, HBD, Tanimoto, afinidades--, que antes solo
                      existian repartidos en un fichero por molecula. */}
                  {resultsPanel.json_resultados && (
                    <button
                      onClick={() => descargarResultado(resultsPanel.json_resultados)}
                      className="btn-csv-download"
                      title="Todas las moléculas con los valores calculados por cada nodo"
                    >
                      📥 Descargar resultados completos (JSON)
                    </button>
                  )}

                  {resultsPanel.ranking && resultsPanel.ranking.length > 0 && (
                    <div className="batch-ranking">
                      <p className="ranking-tipo">
                        Score: <strong>{resultsPanel.tipo_score || '—'}</strong>
                        <span style={{ float: 'right', color: '#94a3b8', fontWeight: 'normal' }}>
                          Top {Math.min(25, resultsPanel.ranking.filter(r=>r.exito).length)}
                        </span>
                      </p>
                      <div className="ranking-barras">
                        {resultsPanel.ranking.filter(r => r.exito && r.score != null).slice(0, 25).map((r, i) => {
                          const pct = normalizarScore(r.score, resultsPanel.ranking, resultsPanel.tipo_score);
                          return (
                            <div key={i} className="ranking-fila">
                              <span className="ranking-pos">{r.posicion}</span>
                              <div className="ranking-barra-wrap">
                                <div
                                  className="ranking-barra"
                                  style={{ width: `${pct}%`, background: colorScore(pct) }}
                                />
                                <span className="ranking-nombre" title={r.nombre}>
                                  {r.nombre.length > 14 ? r.nombre.slice(0, 13) + '…' : r.nombre}
                                </span>
                              </div>
                              <span className="ranking-score">{r.score.toFixed(3)}</span>
                            </div>
                          );
                        })}
                      </div>
                      {resultsPanel.ranking.filter(r=>r.exito).length > 25 && (
                        <p className="ranking-more">
                          … y {resultsPanel.ranking.filter(r=>r.exito).length - 25} más en el CSV
                        </p>
                      )}
                    </div>
                  )}

                  <p className="duration">⏱️ {Math.round(resultsPanel.duracion_segundos)}s</p>
                </div>

              ) : (
                /* ── Modo normal ── */
                <>
                  <div className={`status-badge ${resultsPanel.estado}`}>
                    {resultsPanel.estado?.toUpperCase()}
                  </div>

                  {resultsPanel.errores && resultsPanel.errores.length > 0 && (
                    <div className="errors-section">
                      <h4>⚠️ Errores:</h4>
                      <ul>
                        {resultsPanel.errores.map((err, idx) => (
                          <li key={idx}>{err}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <div className="results-files">
                    <h4>📁 Archivos Resultantes:</h4>
                    {resultsPanel.resultados && Object.entries(resultsPanel.resultados).map(([nId, resultado]) => {
                      const archivo = resultado.archivo || resultado.archivo_salida || resultado.archivo_poses;
                      if (!archivo) return null;
                      const nombreArchivo = archivo.replace(/\\/g, '/').split('/').pop();
                      const puede3D = /\.(sdf|mol2|mol|pdb)$/i.test(nombreArchivo);
                      return (
                        <div key={nId} className="result-file">
                          <button
                            onClick={() => descargarResultado(nombreArchivo)}
                            className="download-link"
                          >
                            📥 {nombreArchivo}
                          </button>
                          {puede3D && (
                            <button className="btn-ver3d" style={{ marginLeft: 6 }} onClick={() => setVisor3D(nombreArchivo)}>
                              🔬 3D
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  <p className="duration">⏱️ Duración: {resultsPanel.duracion_segundos}s</p>
                </>
              )}
            </div>
          ) : (
            <div className="no-results">
              <p>Ejecuta un workflow para ver resultados aquí</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default VisualBuilder;
