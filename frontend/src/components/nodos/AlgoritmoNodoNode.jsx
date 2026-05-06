import React, { useState, useEffect } from 'react';
import { Handle, Position } from 'reactflow';
import '../../styles/Nodos.css';

const AlgoritmoNodoNode = ({ data, id }) => {
  const [algoritmos, setAlgoritmos] = useState([]);
  const [seleccionado, setSeleccionado] = useState(null);

  useEffect(() => {
    cargarAlgoritmos();
  }, []);

  const cargarAlgoritmos = async () => {
    try {
      const response = await fetch('http://localhost:8000/algoritmos');
      const data = await response.json();
      setAlgoritmos(data);
      if (data.length > 0) {
        setSeleccionado(data[0].id);
        handleAlgoritmoChange(data[0].id, data[0].nombre);
      }
    } catch (err) {
      console.error('Error cargando algoritmos:', err);
    }
  };

  const handleAlgoritmoChange = (id, nombre) => {
    setSeleccionado(id);
    data.algoritmo_id = id;
    data.algoritmo_nombre = nombre;
  };

  return (
    <div className="nodo algoritmo-nodo">
      <div className="nodo-header">⚙️ Algoritmo</div>
      
      <div className="nodo-body">
        <select 
          value={seleccionado || ''}
          onChange={(e) => {
            const algo = algoritmos.find(a => a.id == e.target.value);
            handleAlgoritmoChange(algo.id, algo.nombre);
          }}
          className="select-algo"
        >
          {algoritmos.map(algo => (
            <option key={algo.id} value={algo.id}>
              {algo.nombre}
            </option>
          ))}
        </select>
        <p className="algo-desc">Aplica el algoritmo seleccionado</p>
      </div>

      <Handle type="input" position={Position.Left} id="input_molecula" />
      <Handle type="output" position={Position.Right} />
    </div>
  );
};

export default AlgoritmoNodoNode;
