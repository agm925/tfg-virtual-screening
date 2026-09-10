import React, { useState, useEffect } from 'react';
import { Handle, Position, useReactFlow } from 'reactflow';
import { apiFetch } from '../../api/client';
import '../../styles/Nodos.css';

const PreprocesadoNodoNode = ({ data, id }) => {
  const { setNodes, setEdges } = useReactFlow();
  const eliminar = (e) => {
    e.stopPropagation();
    setNodes(nds => nds.filter(n => n.id !== id));
    setEdges(eds => eds.filter(e => e.source !== id && e.target !== id));
  };
  const [algoritmos, setAlgoritmos] = useState([]);
  const [seleccionado, setSeleccionado] = useState(String(data.algoritmo_id || ''));
  const [nombreSeleccionado, setNombreSeleccionado] = useState(data.algoritmo_nombre || '');
  const [filtroExpresion, setFiltroExpresion] = useState(data.filtro_expresion || 'MW>200');
  const [sinH, setSinH] = useState(data.sin_h || false);
  const [sin3D, setSin3D] = useState(data.sin_3d || false);
  const [sinCenter, setSinCenter] = useState(data.sin_center || false);
  const [formatoSalida, setFormatoSalida] = useState(data.formato_salida || 'mismo');

  useEffect(() => {
    cargarAlgoritmos();
  }, []);

  const cargarAlgoritmos = async () => {
    try {
      const todos = await apiFetch('/algoritmos').then(r => r.json());
      const filtrados = todos.filter(a => a.tipo === 'preprocesado');
      setAlgoritmos(filtrados);
      if (filtrados.length === 0) return;
      const guardado = filtrados.find(a => String(a.id) === String(data.algoritmo_id));
      const elegido = guardado || filtrados[0];
      handleCambio(elegido.id, elegido.nombre, elegido.ruta_archivo, elegido.clave_score);
    } catch (err) {
      console.error('Error cargando algoritmos de preprocesado:', err);
    }
  };

  // algoritmo_ruta guarda el nombre real del .py; algoritmo_nombre es la
  // etiqueta que ve el usuario. El motor construye la ruta del script con
  // "algoritmo_ruta or algoritmo_nombre", asi que omitirlo aqui funcionaba
  // solo mientras ambos coincidian: en cuanto un algoritmo se registre como
  // "Docking con Smina" en vez de "dockingSmina", el flujo fallaria con
  // "Algoritmo no encontrado: algoritmos/Docking con Smina.py".
  const handleCambio = (id, nombre, rutaArchivo, claveScore) => {
    setSeleccionado(String(id));
    setNombreSeleccionado(nombre);
    data.algoritmo_id     = id;
    data.algoritmo_nombre = nombre;
    data.algoritmo_ruta   = rutaArchivo;
    // clave_score: la anota el banco de pruebas al subir el algoritmo
    // (ver app/banco_pruebas.py). El motor la usa para leer la puntuacion
    // del JSON sin tener que adivinar su nombre.
    data.clave_score      = claveScore;
    if (nombre.toLowerCase().includes('filtroobabel')) {
      data.filtro_expresion = filtroExpresion;
    }
  };

  const esFiltroObabel = nombreSeleccionado.toLowerCase().includes('filtroobabel');
  const esPreparacionObabel = nombreSeleccionado.toLowerCase().includes('preparacionobabel');

  const handleCambioFiltro = (valor) => {
    setFiltroExpresion(valor);
    data.filtro_expresion = valor;
  };

  const handleCambioOpcion = (campo, valor) => {
    if (campo === 'sin_h') { setSinH(valor); data.sin_h = valor; }
    if (campo === 'sin_3d') { setSin3D(valor); data.sin_3d = valor; }
    if (campo === 'sin_center') { setSinCenter(valor); data.sin_center = valor; }
  };

  const handleCambioFormato = (valor) => {
    setFormatoSalida(valor);
    data.formato_salida = valor;
  };

  return (
    <div className="nodo preprocesado-nodo">
      <div className="nodo-header">
        ⚗️ Preprocesar
        <button className="nodo-btn-borrar" onClick={eliminar} title="Eliminar nodo">×</button>
      </div>

      <div className="nodo-body">
        <select
          className="select-algo"
          value={seleccionado}
          onChange={(e) => {
            const algo = algoritmos.find(a => String(a.id) === e.target.value);
            if (algo) handleCambio(algo.id, algo.nombre, algo.ruta_archivo, algo.clave_score);
          }}
        >
          {algoritmos.length > 0
            ? algoritmos.map(algo => (
                <option key={algo.id} value={String(algo.id)}>{algo.nombre}</option>
              ))
            : <option value="">Sin algoritmos de preprocesado</option>}
        </select>

        {esFiltroObabel && (
          <input
            type="text"
            className="select-input"
            value={filtroExpresion}
            placeholder='Expresión, ej: MW>200'
            onChange={(e) => handleCambioFiltro(e.target.value)}
          />
        )}

        {esPreparacionObabel && (
          <>
            <select className="select-input" value={formatoSalida} onChange={(e) => handleCambioFormato(e.target.value)}>
              <option value="mismo">Formato salida: igual que entrada</option>
              <option value="sdf">Formato salida: SDF</option>
              <option value="mol2">Formato salida: MOL2</option>
              <option value="pdbqt">Formato salida: PDBQT</option>
              <option value="pdb">Formato salida: PDB</option>
              <option value="mol">Formato salida: MOL</option>
              <option value="xyz">Formato salida: XYZ</option>
            </select>

            <div className="opciones-checkbox">
              <label>
                <input type="checkbox" checked={!sinH} onChange={(e) => handleCambioOpcion('sin_h', !e.target.checked)} />
                Añadir hidrógenos (pH 7.4)
              </label>
              <label>
                <input type="checkbox" checked={!sin3D} onChange={(e) => handleCambioOpcion('sin_3d', !e.target.checked)} />
                Generar 3D
              </label>
              <label>
                <input type="checkbox" checked={!sinCenter} onChange={(e) => handleCambioOpcion('sin_center', !e.target.checked)} />
                Centrar molécula
              </label>
            </div>
          </>
        )}

        <p className="algo-desc">Conversión, hidrógenos, 3D, filtro Lipinski</p>
      </div>

      <Handle type="target" position={Position.Left}  id="input_molecula" />
      <Handle type="source" position={Position.Right} id="output" />
    </div>
  );
};

export default PreprocesadoNodoNode;
