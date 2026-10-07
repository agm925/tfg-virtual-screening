import React, { useState, useEffect } from 'react';
import { Handle, Position } from 'reactflow';
import { apiFetch } from '../../api/client';
import MarcoNodo from './MarcoNodo';

const AlgoritmoNodoNode = ({ data, id }) => {
  const [algoritmos, setAlgoritmos] = useState([]);
  // Valor siempre como string para evitar mismatch número/string en el select
  const [seleccionado, setSeleccionado] = useState(String(data.algoritmo_id || ''));

  useEffect(() => { cargarAlgoritmos(); }, []);

  const cargarAlgoritmos = async () => {
    try {
      const todos = await apiFetch('/algoritmos').then(r => r.json());
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
    <MarcoNodo id={id} tipo="alineacion" data={data}>
      <div className="nodo-body">
        <select
          className="select-algo"
          aria-label="Algoritmo de alineación"
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
        <p className="nodo-nota">
          Conecta la molécula al punto de arriba y, si quieres, la referencia al de abajo.
        </p>
      </div>
      <Handle type="target" position={Position.Left}  id="input_molecula"   title="Molécula"   style={{ top: '35%' }} />
      <Handle type="target" position={Position.Left}  id="input_referencia" title="Referencia (opcional)" style={{ top: '70%' }} />
      <Handle type="source" position={Position.Right} id="output" />
    </MarcoNodo>
  );
};

export default AlgoritmoNodoNode;
