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
import '../styles/KnimeBuilder.css';

// Componentes de nodos personalizados
import UploadNodoNode from './nodos/UploadNodoNode';
import AlgoritmoNodoNode from './nodos/AlgoritmoNodoNode';
import ComparacionNodoNode from './nodos/ComparacionNodoNode';
import EjecutarNodoNode from './nodos/EjecutarNodoNode';
import DescargarNodoNode from './nodos/DescargarNodoNode';
import SelectDBNodoNode from './nodos/SelectDBNodoNode';
import SelectMolNodoNode from './nodos/SelectMolNodoNode';

// Hook personalizado para llamadas API
import useWorkflowAPI from '../hooks/useWorkflowAPI';

const nodeTypes = {
  upload: UploadNodoNode,
  algoritmo: AlgoritmoNodoNode,
  comparacion: ComparacionNodoNode,
  ejecutar: EjecutarNodoNode,
  descargar: DescargarNodoNode,
  selectDB: SelectDBNodoNode,
  selectMol: SelectMolNodoNode,
};

const KnimeBuilder = ({ usuario }) => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [workflows, setWorkflows] = useState([]);
  const [workflowActual, setWorkflowActual] = useState(null);
  const [resultsPanel, setResultsPanel] = useState(null);
  const [ejecutando, setEjecutando] = useState(false);
  const [nodoId, setNodoId] = useState(0);

  const {
    crearWorkflow,
    actualizarWorkflow,
    obtenerWorkflows,
    ejecutarWorkflow,
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
    { tipo: 'upload', label: '📤 Upload Molécula', color: '#3498db' },
    { tipo: 'selectDB', label: '📂 Seleccionar BD', color: '#9b59b6' },
    { tipo: 'selectMol', label: '🧬 Seleccionar Molécula', color: '#e74c3c' },
    { tipo: 'algoritmo', label: '⚙️ Algoritmo', color: '#2ecc71' },
    { tipo: 'comparacion', label: '🔍 Comparación', color: '#f39c12' },
    { tipo: 'ejecutar', label: '▶️ Ejecutar', color: '#1abc9c' },
    { tipo: 'descargar', label: '📥 Descargar', color: '#34495e' },
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
        descripcion: "Workflow KNIME",
        grafo_json: { nodes: [], edges: [] },
      }, usuario.id);
      
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
  const cargarWorkflow = (workflow) => {
    setWorkflowActual(workflow);
    const grafo = workflow.grafo_json || { nodes: [], edges: [] };
    setNodes(grafo.nodes || []);
    setEdges(grafo.edges || []);
    setResultsPanel(null);
  };

  // Ejecutar workflow
  const ejecutar = async () => {
    if (!workflowActual || nodes.length === 0) {
      alert("No hay workflow para ejecutar");
      return;
    }

    setEjecutando(true);
    try {
      const resultado = await ejecutarWorkflow(workflowActual.id, usuario.id);
      setResultsPanel(resultado);
      
      // Actualizar estado visual de nodos
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
    } catch (err) {
      alert("Error ejecutando workflow: " + err.message);
    } finally {
      setEjecutando(false);
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

  return (
    <div className="knime-container">
      {/* BARRA SUPERIOR */}
      <div className="knime-toolbar">
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
            disabled={!workflowActual || ejecutando || nodes.length === 0}
          >
            {ejecutando ? '⏳ Ejecutando...' : '▶️ Ejecutar Workflow'}
          </button>
        </div>
      </div>

      <div className="knime-content">
        {/* PALETA DE NODOS (Izquierda) */}
        <div className="knime-sidebar-left">
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
        <div className="knime-canvas-wrapper react-flow-wrapper" onDragOver={onDragOver} onDrop={onDrop}>
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
        <div className="knime-sidebar-right">
          <h3>📊 Resultados</h3>
          {resultsPanel ? (
            <div className="results-panel">
              <div className={`status-badge ${resultsPanel.estado}`}>
                {resultsPanel.estado.toUpperCase()}
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
                {resultsPanel.resultados && Object.entries(resultsPanel.resultados).map(([nodoId, resultado]) => (
                  resultado.tipo === 'descargar' && (
                    <div key={nodoId} className="result-file">
                      <a 
                        href={`/descargar?archivo=${resultado.archivo}`}
                        download
                        className="download-link"
                      >
                        📥 {resultado.archivo}
                      </a>
                    </div>
                  )
                ))}
              </div>

              <p className="duration">
                ⏱️ Duración: {resultsPanel.duracion_segundos}s
              </p>
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

export default KnimeBuilder;
