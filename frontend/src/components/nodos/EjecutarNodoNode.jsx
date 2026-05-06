import React from 'react';
import { Handle, Position } from 'reactflow';
import '../../styles/Nodos.css';

const EjecutarNodoNode = ({ data, id }) => {
  return (
    <div className="nodo ejecutar-nodo">
      <div className="nodo-header">▶️ Ejecutar</div>
      
      <div className="nodo-body">
        <p>Marca el inicio de ejecución del workflow</p>
      </div>

      <Handle type="output" position={Position.Right} />
    </div>
  );
};

export default EjecutarNodoNode;
