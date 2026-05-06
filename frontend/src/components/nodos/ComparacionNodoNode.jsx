import React from 'react';
import { Handle, Position } from 'reactflow';
import '../../styles/Nodos.css';

const ComparacionNodoNode = ({ data, id }) => {
  return (
    <div className="nodo comparacion-nodo">
      <div className="nodo-header">🔍 Comparación (Tanimoto)</div>
      
      <div className="nodo-body">
        <p>Compara similitud química entre dos moléculas</p>
      </div>

      <Handle type="input" position={Position.Left} id="input_mol1" />
      <Handle type="input" position={Position.Bottom} id="input_mol2" />
      <Handle type="output" position={Position.Right} />
    </div>
  );
};

export default ComparacionNodoNode;
