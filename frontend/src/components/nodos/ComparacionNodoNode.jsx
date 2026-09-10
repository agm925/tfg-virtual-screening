import React, { useState, useEffect } from 'react';
import { Handle, Position, useReactFlow } from 'reactflow';
import { apiFetch } from '../../api/client';
import '../../styles/Nodos.css';

const ComparacionNodoNode = ({ data, id }) => {
  const { setNodes, setEdges } = useReactFlow();
  const [algoritmos, setAlgoritmos] = useState([]);
  const [seleccionado, setSeleccionado] = useState(String(data.algoritmo_id || ''));

  const eliminar = (e) => {
    e.stopPropagation();
    setNodes(nds => nds.filter(n => n.id !== id));
    setEdges(eds => eds.filter(e => e.source !== id && e.target !== id));
  };

  useEffect(() => { cargarAlgoritmos(); }, []);

  const cargarAlgoritmos = async () => {
    try {
      const todos = await apiFetch('/algoritmos').then(r => r.json());
      const filtrados = todos.filter(a => a.tipo === 'comparacion');
      setAlgoritmos(filtrados);
      if (filtrados.length === 0) return;
      const guardado = filtrados.find(a => String(a.id) === String(data.algoritmo_id));
      const elegido = guardado || filtrados[0];
      aplicarCambio(elegido.id, elegido.nombre, elegido.ruta_archivo, elegido.clave_score);
    } catch (err) { console.error('Error cargando algoritmos:', err); }
  };

    // clave_score: la anota el banco de pruebas al subir el algoritmo
    // (ver app/banco_pruebas.py). El motor la usa para leer la puntuacion
    // del JSON sin tener que adivinar su nombre.
  const aplicarCambio = (algId, nombre, rutaArchivo, claveScore) => {
    setSeleccionado(String(algId));
    data.algoritmo_id         = algId;
    data.algoritmo_nombre     = nombre;
    data.algoritmo_ruta       = rutaArchivo; // nombre real del .py, sin la carpeta
    data.clave_score          = claveScore;
  };

  return (
    <div className="nodo comparacion-nodo">
      <div className="nodo-header">
        ⚖️ Comparar
        <button className="nodo-btn-borrar" onClick={eliminar} title="Eliminar nodo">×</button>
      </div>
      <div className="nodo-body">
        <select
          className="select-algo"
          value={seleccionado}
          onChange={e => {
            const algo = algoritmos.find(a => String(a.id) === e.target.value);
            if (algo) aplicarCambio(algo.id, algo.nombre, algo.ruta_archivo, algo.clave_score);
          }}
        >
          {algoritmos.length > 0
            ? algoritmos.map(a => <option key={a.id} value={String(a.id)}>{a.nombre}</option>)
            : <option value="">Sin algoritmos de comparación</option>}
        </select>
        <p className="algo-desc">Selecciona un algoritmo de comparación</p>
        <p style={{ fontSize: '0.7rem', color: '#95a5a6', marginTop: '0.25rem' }}>
          Molécula 1 → entrada izq. · Molécula 2 → entrada inf.
        </p>
      </div>
      <Handle type="target" position={Position.Left}   id="input_mol1" style={{ top: '35%' }} />
      <Handle type="target" position={Position.Bottom} id="input_mol2" />
      <Handle type="source" position={Position.Right}  id="output" />
    </div>
  );
};

export default ComparacionNodoNode;
