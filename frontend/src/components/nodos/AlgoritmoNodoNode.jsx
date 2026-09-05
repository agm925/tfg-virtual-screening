import React, { useState, useEffect } from 'react';
import { Handle, Position, useReactFlow } from 'reactflow';
import '../../styles/Nodos.css';

const AlgoritmoNodoNode = ({ data, id }) => {
  const { setNodes, setEdges } = useReactFlow();
  const [algoritmos, setAlgoritmos] = useState([]);
  // Valor siempre como string para evitar mismatch número/string en el select
  const [seleccionado, setSeleccionado] = useState(String(data.algoritmo_id || ''));

  const eliminar = (e) => {
    e.stopPropagation();
    setNodes(nds => nds.filter(n => n.id !== id));
    setEdges(eds => eds.filter(e => e.source !== id && e.target !== id));
  };

  useEffect(() => { cargarAlgoritmos(); }, []);

  const cargarAlgoritmos = async () => {
    try {
      const todos = await fetch('http://localhost:8000/algoritmos').then(r => r.json());
      const filtrados = todos.filter(a => a.tipo === 'alineacion');
      setAlgoritmos(filtrados);
      if (filtrados.length === 0) return;
      // Restaurar la selección guardada en data, o elegir el primero
      const guardado = filtrados.find(a => String(a.id) === String(data.algoritmo_id));
      const elegido = guardado || filtrados[0];
      aplicarCambio(elegido.id, elegido.nombre, elegido.ruta_archivo);
    } catch (err) { console.error('Error cargando algoritmos:', err); }
  };

  const aplicarCambio = (algId, nombre, rutaArchivo) => {
    setSeleccionado(String(algId));
    data.algoritmo_id     = algId;
    data.algoritmo_nombre = nombre;
    data.algoritmo_ruta   = rutaArchivo;
  };

  return (
    <div className="nodo alineacion-nodo">
      <div className="nodo-header">
        📐 Alinear
        <button className="nodo-btn-borrar" onClick={eliminar} title="Eliminar nodo">×</button>
      </div>
      <div className="nodo-body">
        <select
          className="select-algo"
          value={seleccionado}
          onChange={e => {
            const algo = algoritmos.find(a => String(a.id) === e.target.value);
            if (algo) aplicarCambio(algo.id, algo.nombre, algo.ruta_archivo);
          }}
        >
          {algoritmos.length > 0
            ? algoritmos.map(a => <option key={a.id} value={String(a.id)}>{a.nombre}</option>)
            : <option value="">Sin algoritmos de alineación</option>}
        </select>
        <p className="algo-desc">Selecciona un algoritmo de alineación</p>
        <p style={{ fontSize: '0.7rem', color: '#95a5a6', marginTop: '0.25rem' }}>
          Molécula → entrada sup. · Referencia → entrada inf. (opcional)
        </p>
      </div>
      <Handle type="target" position={Position.Left}  id="input_molecula"  style={{ top: '35%' }} />
      <Handle type="target" position={Position.Left}  id="input_referencia" style={{ top: '70%' }} />
      <Handle type="source" position={Position.Right} id="output" />
    </div>
  );
};

export default AlgoritmoNodoNode;
