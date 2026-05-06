import React from 'react';
import { Handle, Position } from 'reactflow';
import '../../styles/Nodos.css';

const DescargarNodoNode = ({ data, id }) => {
  return (
    <div className="nodo descargar-nodo">
      <div className="nodo-header">📥 Descargar</div>
      
      <div className="nodo-body">
        <p>Archivo listo para descargar</p>
      </div>

      <Handle type="input" position={Position.Left} />
    </div>
  );
};

export default DescargarNodoNode;
