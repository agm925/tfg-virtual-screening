import React from 'react';
import { Handle, Position } from 'reactflow';
import '../../styles/Nodos.css';

const SelectDBNodoNode = ({ data, id }) => {
  return (
    <div className="nodo selectdb-nodo">
      <div className="nodo-header">📂 Seleccionar BD</div>
      
      <div className="nodo-body">
        <select className="select-input">
          <option>BD Local</option>
          <option>BD Remota</option>
        </select>
      </div>

      <Handle type="output" position={Position.Right} />
    </div>
  );
};

export default SelectDBNodoNode;
