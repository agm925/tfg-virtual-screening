import React, { useState, useCallback, useEffect, useRef } from 'react';
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
import VerEn3D from './VerEn3D';
import Icono from './Icono';
import { TIPOS_NODO } from '../utils/tiposNodo';
import { estaActivo } from '../utils/ficheros';
import { getToken } from '../api/client';
import { mensajeError } from '../utils/mensajes';
import { textoEstado } from '../utils/ficheros';
import { useIdioma } from '../hooks/useIdioma';
import TextoConFormato from './TextoConFormato';
import { claveEditor } from '../utils/almacenamiento';
import { aCoordenadasDelLienzo, posicionNuevoNodo } from '../utils/lienzo';
import { huella, vistaDeEjecucion } from '../utils/ejecucion';
import { SoloLectura } from '../utils/soloLectura';
import '../styles/Nodos.css';

const I_REPRODUCIR = <Icono nombre="reproducir" />;
const I_RELOJ = <Icono nombre="reloj" />;
const I_PROCESANDO = <Icono nombre="procesando" />;

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

// --- Volver al editor sin perder nada (spec 001, H3) ---
//
// El editor se desmonta al cambiar de pagina (App.jsx pinta una sola a la
// vez), y con el se perdian el workflow abierto y el panel de resultados. Se
// guarda en sessionStorage la ULTIMA VERSION GUARDADA del grafo (no lo que hay
// en el lienzo), el workflow y la ultima ejecucion: dura lo que la pestana y
// es solo de este navegador. Los cambios sin guardar no se conservan: al
// salir con cambios se pregunta antes (confirmarDescarte), que es lo que se
// decidio para la plataforma. La clave lleva el usuario para que otra cuenta
// en la misma pestana no lo herede, y App.jsx lo borra al cerrar sesion
// (olvidarSesion, utils/almacenamiento.js, spec 004).
const claveBorrador = (usuario) => claveEditor(usuario?.id);

const leerBorrador = (usuario) => {
  try {
    return JSON.parse(sessionStorage.getItem(claveBorrador(usuario)));
  } catch {
    return null; // ilegible o sin acceso: se empieza de cero
  }
};

// Lo que se guarda de un grafo: sin las marcas de la ultima ejecucion ni lo que
// React Flow anade para pintar (width, selected, dragging...). Es lo que se
// manda al servidor y lo que se compara para saber si hay cambios sin guardar.
const grafoGuardable = (nodes, edges) => ({
  nodes: nodes.map(({ id, type, position, data }) => {
    const datos = { ...data };
    delete datos.ejecutado;
    delete datos.error;
    return { id, type, position: { x: Math.round(position.x), y: Math.round(position.y) }, data: datos };
  }),
  edges: edges.map(({ id, source, target, sourceHandle, targetHandle }) =>
    ({ id, source, target, sourceHandle, targetHandle })),
});

const GRAFO_VACIO = { nodes: [], edges: [] };

const resumenWorkflow = (wf) => wf && { id: wf.id, nombre: wf.nombre, descripcion: wf.descripcion };

// Los ids de nodo son tipo_<n>: los nuevos siguen al mayor ya usado, para no
// chocar con los de un borrador restaurado.
const siguienteNodoId = (nodos) =>
  Math.max(-1, ...(nodos || []).map(n => Number(String(n.id).split('_').pop()) || 0)) + 1;

// «Ver workflow» desde Resultados o Inicio (spec 012): lo que se dice sobre el
// lienzo segun lo que se esta viendo (utils/ejecucion.js, vistaDeEjecucion):
// la clave de su texto en los diccionarios.
const TEXTO_VISTA = {
  consulta: 'constructor.vista_consulta',
  borrado: 'constructor.vista_borrado',
  'sin-copia': 'constructor.vista_sin_copia',
};

// `salidaRef`: App.jsx la consulta antes de cambiar de pagina o cerrar
// sesion; aqui se deja en ella la funcion que pregunta si hay cambios.
// `llegada`: {workflow_id, ejecucion_id, workflow_nombre} de un «Ver
// workflow» de otra pagina (spec 012), que se consume una vez (`alLlegar`).
const VisualBuilder = ({ usuario, crearAlAbrir = false, alCrearAlAbrir, salidaRef, abrirEnVisor, llegada, alLlegar }) => {
  const { t } = useIdioma();
  // El borrador se lee una vez, como estado inicial. Si se llega desde "Nuevo
  // workflow" se empieza uno nuevo, y desde «Ver workflow» lo que se pidio.
  const [borrador] = useState(() => (crearAlAbrir || llegada ? null : leerBorrador(usuario)));
  const [nodes, setNodes, onNodesChange] = useNodesState(conPosicion(borrador?.grafo?.nodes));
  const [edges, setEdges, onEdgesChange] = useEdgesState(borrador?.grafo?.edges || []);
  const [workflows, setWorkflows] = useState([]);
  const [workflowActual, setWorkflowActual] = useState(borrador?.workflowActual || null);
  const [resultsPanel, setResultsPanel] = useState(null);
  const [ejecutando,       setEjecutando]       = useState(false);
  const [estadoEjecucion,  setEstadoEjecucion]  = useState(null); // 'pendiente'|'procesando'|null
  const [batchProgreso,    setBatchProgreso]     = useState(null); // { actual, total, molecula_actual }
  const [nodoId, setNodoId] = useState(() => siguienteNodoId(borrador?.grafo?.nodes));
  // {tipo: 'consulta'|'borrado'|'sin-copia', ejecucionId} cuando se ve el
  // workflow de una ejecucion que no es la version actual editable (spec 012).
  // En 'consulta' y 'borrado' no se puede cambiar nada: es lo que se ejecuto.
  const [vistaEjecucion, setVistaEjecucion] = useState(borrador?.vista || null);
  const soloLectura = vistaEjecucion?.tipo === 'consulta' || vistaEjecucion?.tipo === 'borrado';
  const esperaRef = useRef(null); // AbortController de la espera en curso
  // Aviso en la propia pagina { tipo: 'exito'|'error', texto }. Antes eran
  // alert(), que bloquean la pantalla y enseñaban el err.message tal cual.
  const [aviso, setAviso] = useState(null);
  // En el móvil la paleta y los resultados son paneles que se abren encima
  // del lienzo, de uno en uno (spec 010). En escritorio no se usa: los dos
  // están siempre a los lados.
  const [panelMovil, setPanelMovil] = useState(null); // 'paleta' | 'resultados' | null
  const alternarPanel = (panel) => setPanelMovil(p => (p === panel ? null : panel));
  const avisar = (tipo, texto) => setAviso({ tipo, texto });

  // Los de exito se van solos; los de error se quedan hasta cerrarlos, para
  // que de tiempo a leerlos.
  useEffect(() => {
    if (aviso?.tipo !== 'exito') return;
    const t = setTimeout(() => setAviso(null), 4000);
    return () => clearTimeout(t);
  }, [aviso]);

  const {
    crearWorkflow,
    actualizarWorkflow,
    obtenerWorkflows,
    obtenerWorkflow,
    ejecutarWorkflow,
    esperarEjecucion,
    obtenerEjecucion,
    descargarResultado
  } = useWorkflowAPI();

  // Deja de esperar a la ejecucion en curso (el trabajo sigue en el servidor;
  // solo se deja de mirar). Se llama al cambiar de workflow y al salir del
  // editor: antes el sondeo seguia y acababa pintando los resultados de un
  // workflow sobre otro.
  const cortarEspera = () => {
    esperaRef.current?.abort();
    esperaRef.current = null;
  };

  // Ultima version guardada (o recien cargada) y lo que hay en el lienzo.
  // `actualRef` existe porque los nodos cambian sus datos sobre el propio
  // objeto (data.algoritmo_id = ...) sin pasar por setNodes: al comparar hay
  // que mirar los objetos de ahora, no los del ultimo render.
  const borradorRef = useRef(borrador || { grafo: GRAFO_VACIO, workflowActual: null, ejecucionId: null });
  const actualRef = useRef({ nodes, edges });
  useEffect(() => { actualRef.current = { nodes, edges }; }, [nodes, edges]);
  const soloLecturaRef = useRef(soloLectura);
  useEffect(() => { soloLecturaRef.current = soloLectura; }, [soloLectura]);

  const escribirBorrador = (cambios) => {
    borradorRef.current = { ...borradorRef.current, ...cambios };
    // Sin token es que se esta cerrando la sesion: App.jsx acaba de borrarlo.
    if (!getToken()) return;
    try {
      sessionStorage.setItem(claveBorrador(usuario), JSON.stringify(borradorRef.current));
    } catch { /* sin almacenamiento (modo privado, cuota): no se recupera al volver */ }
  };

  // `grafo` ya en forma guardable. Se copia: los nodos seguiran cambiando sus
  // `data` sobre los objetos del lienzo.
  const marcarGuardado = (grafo, wf, ejecucion = borradorRef.current.ejecucionId) =>
    escribirBorrador({
      grafo: JSON.parse(JSON.stringify(grafo)),
      workflowActual: resumenWorkflow(wf),
      ejecucionId: ejecucion,
    });

  const hayCambios = () => {
    // En modo consulta no se puede cambiar nada que guardar; si un nodo
    // completa sus `data` al montarse (el nombre de su algoritmo), no cuenta.
    if (soloLecturaRef.current) return false;
    const { nodes: n, edges: e } = actualRef.current;
    return huella(grafoGuardable(n, e)) !== huella(borradorRef.current.grafo);
  };

  // Antes de perder lo que hay en el lienzo (otra pagina, otro workflow,
  // cerrar sesion): true si no hay cambios o si el usuario acepta perderlos.
  const confirmarDescarte = () => !hayCambios() || window.confirm(t('constructor.sin_guardar'));

  const ponerVista = (vista) => {
    setVistaEjecucion(vista);
    escribirBorrador({ vista });
  };

  // Pone un grafo en el lienzo como ultima version guardada.
  const mostrarGrafo = (grafo, workflow, ejecucionId) => {
    setWorkflowActual(workflow);
    const nodos = conPosicion(grafo.nodes);
    setNodes(nodos);
    setEdges(grafo.edges || []);
    setNodoId(siguienteNodoId(grafo.nodes));
    setResultsPanel(null);
    marcarGuardado(grafoGuardable(nodos, grafo.edges || []), workflow, ejecucionId);
  };

  useEffect(() => {
    if (!salidaRef) return;
    salidaRef.current = confirmarDescarte;
    return () => { salidaRef.current = null; };
  });

  // Cerrar o recargar la pestana: el navegador muestra su propio aviso (no
  // deja poner un texto) si hay cambios sin guardar.
  useEffect(() => {
    const alDescargar = (e) => {
      if (!hayCambios()) return;
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', alDescargar);
    return () => window.removeEventListener('beforeunload', alDescargar);
  }, []);

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

  // Drag-drop de nodos desde la paleta
  const onDragStart = (event, tipo) => {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('tipo', tipo);
  };

  const onDragOver = (event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  };

  // La instancia de React Flow, para saber cuánto está desplazado y ampliado
  // el lienzo (onInit).
  const flujo = useRef(null);
  const vistaDelLienzo = () => flujo.current?.getViewport() ?? { x: 0, y: 0, zoom: 1 };

  const onDrop = (event) => {
    event.preventDefault();
    if (soloLectura) return;
    const tipo = event.dataTransfer.getData('tipo');
    const caja = event.currentTarget.getBoundingClientRect();
    // Con el desplazamiento y el zoom del lienzo: antes se tomaba el punto de
    // la pantalla tal cual, y con el lienzo movido o ampliado el nodo caía
    // lejos de donde se soltaba.
    añadirNodo(tipo, aCoordenadasDelLienzo(
      { x: event.clientX - caja.left, y: event.clientY - caja.top }, vistaDelLienzo()));
  };

  // Tocar (o pulsar Enter sobre) un nodo de la paleta lo añade en el centro
  // de lo que se ve (spec 010): en el móvil el arrastre del navegador no
  // funciona con el dedo, y con el teclado tampoco había forma de añadirlo.
  const añadirAlTocar = (tipo) => {
    const caja = document.querySelector('.react-flow-wrapper').getBoundingClientRect();
    añadirNodo(tipo, posicionNuevoNodo({
      ancho: caja.width, alto: caja.height, viewport: vistaDelLienzo(), nodos: nodes,
    }));
    setPanelMovil(null);   // en el móvil, para ver dónde ha caído
  };

  const añadirNodo = (tipo, position) => {
    const nuevoNodo = {
      id: `${tipo}_${nodoId}`,
      type: tipo,
      position,
      // Sin `label`: el nombre visible sale de tiposNodo.js segun `type`, y
      // nadie (ni los nodos ni el backend) leia el que se guardaba aqui.
      data: {},
    };

    setNodes((nds) => [...nds, nuevoNodo]);
    setNodoId(nodoId + 1);
  };

  // Crear nuevo workflow
  const crearNuevo = async () => {
    if (!confirmarDescarte()) return;
    const nombre = prompt(t('constructor.nombre_workflow'));
    if (!nombre) return;

    try {
      const nuevoWf = await crearWorkflow({
        nombre,
        descripcion: "Workflow visual",
        grafo_json: { nodes: [], edges: [] },
      });

      cortarEspera();
      ponerVista(null);
      setWorkflowActual(nuevoWf);
      setNodes([]);
      setEdges([]);
      setResultsPanel(null);
      marcarGuardado(GRAFO_VACIO, nuevoWf, null);
      cargarWorkflows();
    } catch (err) {
      avisar('error', mensajeError(t('accion.crear_workflow'), err, t));
    }
  };

  // Llegada desde "Nuevo workflow" (cabecera o Inicio): se crea uno al abrir,
  // y se avisa para que la proxima visita al constructor no lo repita. La
  // referencia evita pedir el nombre dos veces cuando React ejecuta el efecto
  // por duplicado (StrictMode, en desarrollo).
  const creadoAlAbrir = useRef(false);
  useEffect(() => {
    if (!crearAlAbrir || creadoAlAbrir.current) return;
    creadoAlAbrir.current = true;
    alCrearAlAbrir?.();
    crearNuevo();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [crearAlAbrir]);

  // Guardar workflow actual
  const guardarWorkflow = async () => {
    if (!workflowActual) {
      avisar('error', t('constructor.nada_que_guardar'));
      return;
    }

    try {
      const grafo = grafoGuardable(nodes, edges);
      await actualizarWorkflow(workflowActual.id, {
        nombre: workflowActual.nombre,
        descripcion: workflowActual.descripcion,
        grafo_json: grafo,
      });
      marcarGuardado(grafo, workflowActual);
      avisar('exito', t('constructor.guardado'));
      cargarWorkflows();
    } catch (err) {
      avisar('error', mensajeError(t('accion.guardar_workflow'), err, t));
    }
  };


  const cargarWorkflow = (workflow) => {
    if (!confirmarDescarte()) return;
    cortarEspera();
    ponerVista(null);
    mostrarGrafo(workflow.grafo_json || GRAFO_VACIO, workflow, null);
  };


  const marcarNodos = (resultado) => {
    if (!resultado?.resultados) return;
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
  };

  // Espera a que termine una ejecucion ya encolada y pinta su resultado. La
  // usan ejecutar() y la vuelta al editor con una ejecucion todavia en curso.
  const seguirEjecucion = async (id) => {
    cortarEspera();
    const espera = new AbortController();
    esperaRef.current = espera;
    setEjecutando(true);
    setPanelMovil('resultados');   // en el móvil, para ver el progreso
    try {
      // Polling cada 3 s hasta que el worker termine
      const resultado = await esperarEjecucion(id, (datos) => {
        setEstadoEjecucion(datos.estado);
        const rj = datos.resultados_json;
        if (rj && rj.modo === 'batch' && rj.total > 0) {
          setBatchProgreso({ actual: rj.progreso, total: rj.total, molecula: rj.molecula_actual });
        }
      }, espera.signal);
      setResultsPanel(resultado);
      marcarNodos(resultado);
    } catch (err) {
      // Cortada a proposito (otro workflow, o se ha salido del editor): no es
      // un error y no hay nada que pintar.
      if (err.name === 'AbortError') return;
      avisar('error', mensajeError(t('accion.ejecutar_workflow'), err, t));
    } finally {
      if (esperaRef.current === espera) {
        esperaRef.current = null;
        setEjecutando(false);
        setEstadoEjecucion(null);
        setBatchProgreso(null);
      }
    }
  };

  // Ejecutar workflow — encola en Celery y hace polling hasta que termina
  const ejecutar = async () => {
    if (nodes.length === 0) {
      avisar('error', t('constructor.sin_nodos'));
      return;
    }

    setAviso(null);
    ponerVista(null);   // los resultados nuevos ya son de esta version
    setEjecutando(true);
    setEstadoEjecucion('pendiente');
    setResultsPanel(null);
    setBatchProgreso(null);
    // Las marcas de la ejecucion anterior no valen para esta: se quitan del
    // lienzo, y grafoGuardable tampoco las manda al servidor.
    const grafo = grafoGuardable(nodes, edges);
    setNodes(nds => nds.map(n => {
      const data = { ...n.data };
      delete data.ejecutado;
      delete data.error;
      return { ...n, data };
    }));
    let nuevaEjecucion;
    try {
      // Auto-crear workflow si no existe
      let wf = workflowActual;
      if (!wf) {
        const nombre = prompt(t('constructor.nombre_workflow_auto')) || t('constructor.sin_nombre');
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
        grafo_json: grafo,
      });
      marcarGuardado(grafo, wf);

      // Encolar tarea Celery → devuelve { ejecucion_id } inmediatamente
      ({ ejecucion_id: nuevaEjecucion } = await ejecutarWorkflow(wf.id));
      escribirBorrador({ ejecucionId: nuevaEjecucion });
    } catch (err) {
      avisar('error', mensajeError(t('accion.ejecutar_workflow'), err, t));
      setEjecutando(false);
      setEstadoEjecucion(null);
      return;
    }
    await seguirEjecucion(nuevaEjecucion);
  };

  // La ultima ejecucion del borrador: si sigue en marcha se vuelve a esperar,
  // y si ya termino se pinta su resultado.
  const recuperarEjecucion = async (id) => {
    try {
      const datos = await obtenerEjecucion(id);
      if (estaActivo(datos.estado)) {
        await seguirEjecucion(id);
      } else {
        setResultsPanel(datos.resultados_json || {});
        marcarNodos(datos.resultados_json);
      }
    } catch {
      // Ya no existe o no se puede consultar: queda el lienzo, sin panel.
      escribirBorrador({ ejecucionId: null });
    }
  };

  // «Ver workflow» (spec 012): el grafo que dio los resultados de una
  // ejecucion, con esos resultados en el panel. No se pregunta por cambios
  // sin guardar: se llega desde otra pagina, y al salir de aqui ya se pregunto.
  const abrirEjecucion = async ({ workflow_id, ejecucion_id, workflow_nombre }) => {
    cortarEspera();
    setAviso(null);
    setPanelMovil('resultados');   // en el móvil, lo que se ha venido a ver
    let ejecucion;
    let actual = null;
    try {
      ejecucion = await obtenerEjecucion(ejecucion_id);
      if (!ejecucion.workflow_borrado) actual = await obtenerWorkflow(workflow_id);
    } catch (err) {
      ponerVista(null);
      mostrarGrafo(GRAFO_VACIO, null, null);
      avisar('error', mensajeError(t('accion.abrir_workflow_ejecucion'), err, t));
      return;
    }
    const tipo = vistaDeEjecucion(ejecucion, actual);
    const conCopia = tipo === 'consulta' || tipo === 'borrado';
    mostrarGrafo((conCopia ? ejecucion.grafo_json : actual.grafo_json) || GRAFO_VACIO,
                 actual || { id: workflow_id, nombre: workflow_nombre }, ejecucion_id);
    ponerVista(tipo === 'actual' ? null : { tipo, ejecucionId: ejecucion_id });
    if (estaActivo(ejecucion.estado)) {
      seguirEjecucion(ejecucion_id);
    } else {
      setResultsPanel(ejecucion.resultados_json || {});
      marcarNodos(ejecucion.resultados_json);
    }
  };

  const abrirVersionActual = async () => {
    try {
      cargarWorkflow(await obtenerWorkflow(workflowActual.id));
    } catch (err) {
      avisar('error', mensajeError(t('accion.abrir_version_actual'), err, t));
    }
  };

  // Como crearAlAbrir: la referencia evita atenderla dos veces cuando React
  // ejecuta el efecto por duplicado (StrictMode, en desarrollo).
  const llegadaAtendida = useRef(false);
  useEffect(() => {
    if (!llegada || llegadaAtendida.current) return;
    llegadaAtendida.current = true;
    alLlegar?.();
    abrirEjecucion(llegada);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [llegada]);

  useEffect(() => {
    // Consultar al servidor al montar es justo para lo que sirve un efecto; el
    // aviso salta por el setCargando que obtenerEjecucion hace al empezar, un
    // estado del hook que este componente ni lee.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (borrador?.ejecucionId) recuperarEjecucion(borrador.ejecucionId);
    return cortarEspera;
    // Solo al montar y desmontar.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Limpiar canvas
  const limpiar = () => {
    if (window.confirm(t('constructor.confirmar_limpiar'))) {
      cortarEspera();
      ponerVista(null);
      setNodes([]);
      setEdges([]);
      setWorkflowActual(null);
      setResultsPanel(null);
      marcarGuardado(GRAFO_VACIO, null, null);
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

  return (
    <div className="visual-container">
      {/* BARRA SUPERIOR */}
      <div className="visual-toolbar">
        <div className="toolbar-left">
          <button onClick={crearNuevo} className="btn btn-primary">
            <Icono nombre="mas" />{t('cabecera.nuevo_workflow')}
          </button>
          <button onClick={guardarWorkflow} className="btn btn-secondary" disabled={!workflowActual || soloLectura}>
            <Icono nombre="guardar" />{t('constructor.guardar')}
          </button>
          <button onClick={limpiar} className="btn btn-danger">
            <Icono nombre="papelera" />{t('constructor.limpiar')}
          </button>
        </div>

        <div className="toolbar-center">
          <select
            className="workflow-select"
            onChange={(e) => {
              if (e.target.value === '') return;
              cargarWorkflow(workflows[e.target.value]);
              e.target.value = '';
            }}
          >
            <option value="">{t('constructor.cargar_workflow')}</option>
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
            disabled={ejecutando || nodes.length === 0 || soloLectura}
          >
            {!ejecutando && <>{I_REPRODUCIR}{t('constructor.ejecutar')}</>}
            {ejecutando && estadoEjecucion === 'pendiente'  && <>{I_RELOJ}{t('constructor.en_cola')}</>}
            {ejecutando && estadoEjecucion === 'procesando' && batchProgreso
              && <>{I_PROCESANDO}{t('constructor.progreso_corto', { actual: batchProgreso.actual, total: batchProgreso.total })}</>}
            {ejecutando && estadoEjecucion === 'procesando' && !batchProgreso && <>{I_PROCESANDO}{t('constructor.procesando')}</>}
            {ejecutando && !estadoEjecucion                 && <>{I_RELOJ}{t('constructor.encolando')}</>}
          </button>
        </div>
      </div>

      {/* Solo en el móvil (ver visualBuilder.css). */}
      <div className="barra-paneles-movil">
        <button type="button" aria-expanded={panelMovil === 'paleta'} aria-controls="paleta-nodos"
                className={panelMovil === 'paleta' ? 'activo' : ''} onClick={() => alternarPanel('paleta')}
                disabled={soloLectura}>
          <Icono nombre="mas" />{t('constructor.anadir_nodo')}
        </button>
        <button type="button" aria-expanded={panelMovil === 'resultados'} aria-controls="panel-resultados"
                className={panelMovil === 'resultados' ? 'activo' : ''} onClick={() => alternarPanel('resultados')}>
          <Icono nombre="grafico" />{t('cabecera.resultados')}
        </button>
      </div>

      <div className="visual-content">
        {/* PALETA DE NODOS (Izquierda) */}
        <div id="paleta-nodos" className={`visual-sidebar-left ${panelMovil === 'paleta' ? 'abierto' : ''}`}>
          <h3>{t('constructor.nodos_disponibles')}</h3>
          <div className="paleta-nodos">
            {TIPOS_NODO.map((nodo) => (
              <button
                type="button"
                key={nodo.tipo}
                draggable={!soloLectura}
                disabled={soloLectura}
                onDragStart={(e) => onDragStart(e, nodo.tipo)}
                onClick={() => añadirAlTocar(nodo.tipo)}
                className={`nodo-paleta familia-${nodo.familia}`}
              >
                <Icono nombre={nodo.icono} />{t(nodo.etiqueta)}
              </button>
            ))}
          </div>
          <p className="hint">{t('constructor.pista_paleta')}</p>
        </div>

        {/* CANVAS REACT FLOW (Centro) */}
        <div className={`visual-canvas-wrapper react-flow-wrapper ${ejecutando ? 'ejecutando' : ''}`}
             onDragOver={onDragOver} onDrop={onDrop}>
          {workflowActual && <h2 className="workflow-title">{workflowActual.nombre}</h2>}
          {aviso && (
            <div className={`aviso-editor ${aviso.tipo === 'error' ? 'error-msg' : 'exito-msg'}`} role="status">
              <Icono nombre={aviso.tipo === 'error' ? 'aviso' : 'ok'} />
              <span>{aviso.texto}</span>
              <button className="aviso-cerrar" onClick={() => setAviso(null)} aria-label={t('constructor.cerrar_aviso')}>
                <Icono nombre="cerrar" tamano={14} />
              </button>
            </div>
          )}
          {vistaEjecucion && (
            <div className="vista-ejecucion" role="status">
              <Icono nombre={soloLectura ? 'candado' : 'aviso'} />
              <span>
                {t(TEXTO_VISTA[vistaEjecucion.tipo], { n: vistaEjecucion.ejecucionId })}
                {vistaEjecucion.tipo === 'consulta' && (
                  <> <button className="btn-enlace" onClick={abrirVersionActual}>{t('constructor.abrir_version_actual')}</button></>
                )}
              </span>
              {/* Sin copia es solo un aviso, y se puede quitar; el modo
                  consulta dura hasta cargar otro workflow. */}
              {!soloLectura && (
                <button className="aviso-cerrar" onClick={() => ponerVista(null)} aria-label={t('constructor.cerrar_aviso')}>
                  <Icono nombre="cerrar" tamano={14} />
                </button>
              )}
            </div>
          )}
          <SoloLectura.Provider value={soloLectura}>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              nodeTypes={nodeTypes}
              onInit={(instancia) => { flujo.current = instancia; }}
              // Modo consulta (spec 012): se puede mover y ampliar el lienzo,
              // pero no los nodos ni sus conexiones.
              nodesDraggable={!soloLectura}
              nodesConnectable={!soloLectura}
              elementsSelectable={!soloLectura}
              deleteKeyCode={soloLectura ? null : 'Backspace'}
              fitView
            >
              <Background />
              {/* El candado de los controles volveria a dejar mover los
                  nodos: en modo consulta no se ofrece. */}
              <Controls showInteractive={!soloLectura} />
              <MiniMap />
            </ReactFlow>
          </SoloLectura.Provider>
        </div>

        {/* PANEL DE RESULTADOS (Derecha) */}
        <div id="panel-resultados" className={`visual-sidebar-right ${panelMovil === 'resultados' ? 'abierto' : ''}`}>
          <h3><Icono nombre="grafico" />{t('cabecera.resultados')}</h3>

          {/* Progreso batch en tiempo real */}
          {ejecutando && batchProgreso && (
            <div className="batch-progress">
              <p className="batch-progress-label">
                <Icono nombre="procesando" /><TextoConFormato texto={t('constructor.progreso', { actual: `**${batchProgreso.actual}**`, total: `**${batchProgreso.total}**` })} />
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
                    <span className="batch-stat ok"><Icono nombre="ok" />{t('constructor.procesadas', { n: resultsPanel.total_exito })}</span>
                    {resultsPanel.total_error > 0 && (
                      <span className="batch-stat err"><Icono nombre="error" />{t('constructor.errores_n', { n: resultsPanel.total_error })}</span>
                    )}
                    {/* Registros del SDF que RDKit no pudo leer, y que por
                        tanto NO se han cribado. Se enseña aunque sea una
                        mala noticia: antes desaparecían sin dejar rastro y el
                        panel decía "N procesadas, 0 errores" sobre una
                        biblioteca de la que faltaba la mitad. */}
                    {resultsPanel.moleculas_descartadas > 0 && (
                      <span
                        className="batch-stat err"
                        title={t('constructor.descartadas_titulo', { registros: resultsPanel.registros_en_fichero, descartadas: resultsPanel.moleculas_descartadas })}
                      >
                        <Icono nombre="aviso" />{t('constructor.sin_leer', { n: resultsPanel.moleculas_descartadas })}
                      </span>
                    )}
                    <span className="batch-stat bd"><Icono nombre="biblioteca" />{resultsPanel.base_de_datos}</span>
                  </div>

                  {/* Un cribado que transforma o filtra moléculas no tiene
                      ranking: su resultado son las moléculas. Ordenar por peso
                      molecular un filtro de Lipinski no dice nada. */}
                  {resultsPanel.modo_resultado === 'transformacion' && (
                    <div className="batch-summary">
                      <span className="batch-stat ok">
                        <Icono nombre="matraz" />{t('constructor.en_fichero', { n: resultsPanel.total_en_fichero ?? 0 })}
                      </span>
                      {resultsPanel.no_cumplen > 0 && (
                        <span className="batch-stat err"><Icono nombre="filtro" />{t('constructor.no_cumplen', { n: resultsPanel.no_cumplen })}</span>
                      )}
                    </div>
                  )}

                  {/* «Ver en 3D» lleva al visor con la lista del SDF en el
                      orden del fichero, que en las poses ya es el del ranking
                      (spec 002, RF-15). Desde aquí pasa por la confirmación
                      de cambios sin guardar, como cualquier salida del editor. */}
                  {resultsPanel.moleculas_resultado && (
                    <div className="batch-resultado-fichero">
                      <button
                        onClick={() => descargarResultado(resultsPanel.moleculas_resultado)}
                        className="btn-csv-download"
                        title={t('constructor.moleculas_titulo')}
                      >
                        <Icono nombre="bajar" />{t('constructor.descargar_moleculas', { formato: resultsPanel.moleculas_resultado.split('.').pop().toUpperCase() })}
                      </button>
                      <VerEn3D fichero={resultsPanel.moleculas_resultado} abrirEnVisor={abrirEnVisor} className="btn-ver3d" />
                    </div>
                  )}

                  {resultsPanel.csv_propiedades && (
                    <button
                      onClick={() => descargarResultado(resultsPanel.csv_propiedades)}
                      className="btn-csv-download"
                    >
                      <Icono nombre="bajar" />{t('constructor.descargar_propiedades')}
                    </button>
                  )}

                  {resultsPanel.csv_ranking && (
                    <button
                      onClick={() => descargarResultado(resultsPanel.csv_ranking)}
                      className="btn-csv-download"
                    >
                      <Icono nombre="bajar" />{t('constructor.descargar_ranking')}
                    </button>
                  )}

                  {resultsPanel.sdf_poses && (
                    <div className="batch-resultado-fichero">
                      <button
                        onClick={() => descargarResultado(resultsPanel.sdf_poses)}
                        className="btn-csv-download"
                        title={t('constructor.poses_titulo')}
                      >
                        <Icono nombre="bajar" />{t('constructor.descargar_poses')}
                      </button>
                      <VerEn3D fichero={resultsPanel.sdf_poses} abrirEnVisor={abrirEnVisor} className="btn-ver3d" />
                    </div>
                  )}

                  {/* El CSV es el ranking: posicion, nombre y score. Este JSON
                      lleva TODAS las moleculas con los numeros de cada nodo
                      --MW, LogP, HBD, Tanimoto, afinidades--, que antes solo
                      existian repartidos en un fichero por molecula. */}
                  {resultsPanel.json_resultados && (
                    <button
                      onClick={() => descargarResultado(resultsPanel.json_resultados)}
                      className="btn-csv-download"
                      title={t('constructor.json_titulo')}
                    >
                      <Icono nombre="bajar" />{t('constructor.descargar_json')}
                    </button>
                  )}

                  {resultsPanel.ranking && resultsPanel.ranking.length > 0 && (
                    <div className="batch-ranking">
                      <p className="ranking-tipo">
                        {t('constructor.score')} <strong>{resultsPanel.tipo_score || '—'}</strong>
                        <span className="ranking-top">
                          {t('constructor.top', { n: Math.min(25, resultsPanel.ranking.filter(r=>r.exito).length) })}
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
                                  style={{ width: `${pct}%` }}
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
                          {t('constructor.mas_en_csv', { n: resultsPanel.ranking.filter(r=>r.exito).length - 25 })}
                        </p>
                      )}
                    </div>
                  )}

                  <p className="duration"><Icono nombre="reloj" />{Math.round(resultsPanel.duracion_segundos)}s</p>
                </div>

              ) : (
                /* ── Modo normal ── */
                <>
                  <div className={`status-badge ${resultsPanel.estado}`}>
                    {textoEstado(resultsPanel.estado, t)?.toUpperCase()}
                  </div>

                  {resultsPanel.errores && resultsPanel.errores.length > 0 && (
                    <div className="errors-section">
                      <h4><Icono nombre="aviso" />{t('constructor.errores')}</h4>
                      <ul>
                        {resultsPanel.errores.map((err, idx) => (
                          <li key={idx}>{err}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <div className="results-files">
                    <h4><Icono nombre="fichero" />{t('constructor.ficheros_resultantes')}</h4>
                    {resultsPanel.resultados && Object.entries(resultsPanel.resultados).map(([nId, resultado]) => {
                      const archivo = resultado.archivo || resultado.archivo_salida || resultado.archivo_poses;
                      if (!archivo) return null;
                      const nombreArchivo = archivo.replace(/\\/g, '/').split('/').pop();
                      return (
                        <div key={nId} className="result-file">
                          <button
                            onClick={() => descargarResultado(nombreArchivo)}
                            className="download-link"
                          >
                            <Icono nombre="bajar" />{nombreArchivo}
                          </button>
                          <VerEn3D fichero={nombreArchivo} abrirEnVisor={abrirEnVisor} className="btn-ver3d" />
                        </div>
                      );
                    })}
                  </div>

                  <p className="duration"><Icono nombre="reloj" />{t('constructor.duracion', { s: resultsPanel.duracion_segundos })}</p>
                </>
              )}
            </div>
          ) : (
            <div className="no-results">
              <p>{t('constructor.sin_resultados')}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default VisualBuilder;
