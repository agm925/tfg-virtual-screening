import React, { useState, useEffect } from 'react';
import { Handle, Position } from 'reactflow';
import { apiFetch } from '../../api/client';
import MarcoNodo from './MarcoNodo';

const ComparacionNodoNode = ({ data, id }) => {
  const [algoritmos, setAlgoritmos] = useState([]);
  const [seleccionado, setSeleccionado] = useState(String(data.algoritmo_id || ''));

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
    <MarcoNodo id={id} tipo="comparacion" data={data}>
      <div className="nodo-body">
        <select
          className="select-algo"
          aria-label="Algoritmo de comparación"
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
        <p className="nodo-nota">
          Conecta una molécula al punto de la izquierda y la otra al de abajo.
        </p>
      </div>
      <Handle type="target" position={Position.Left}   id="input_mol1" title="Primera molécula" style={{ top: '35%' }} />
      <Handle type="target" position={Position.Bottom} id="input_mol2" title="Segunda molécula" />
      <Handle type="source" position={Position.Right}  id="output" />
    </MarcoNodo>
  );
};

export default ComparacionNodoNode;
