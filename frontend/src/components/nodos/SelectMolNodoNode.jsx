import React from 'react';
import { Handle, Position } from 'reactflow';
import '../../styles/Nodos.css';

const SelectMolNodoNode = ({ data, id }) => {
  return (
    <div className="nodo selectmol-nodo">
      <div className="nodo-header">🧬 Seleccionar Molécula</div>
      
      <div className="nodo-body">
        <select className="select-input">
          <option>Molécula 1</option>
          <option>Molécula 2</option>
          <option>Molécula 3</option>
        </select>
      </div>

      <Handle type="input" position={Position.Left} />
      <Handle type="output" position={Position.Right} />
    </div>
  );
};

export default SelectMolNodoNode;
