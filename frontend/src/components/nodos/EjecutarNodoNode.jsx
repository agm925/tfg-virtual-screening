import React from 'react';
import { Handle, Position } from 'reactflow';
import MarcoNodo from './MarcoNodo';

const EjecutarNodoNode = ({ id }) => {
  return (
    <MarcoNodo id={id} tipo="ejecutar">
      <div className="nodo-body">
        <p>Marca el inicio de ejecución del workflow</p>
      </div>
      <Handle type="source" position={Position.Right} id="output" />
    </MarcoNodo>
  );
};

export default EjecutarNodoNode;
