import React from 'react';
import { Handle, Position } from 'reactflow';
import MarcoNodo from './MarcoNodo';

const DescargarNodoNode = ({ id }) => {
  return (
    <MarcoNodo id={id} tipo="descargar">
      <div className="nodo-body">
        <p>Archivo listo para descargar</p>
      </div>
      <Handle type="target" position={Position.Left} id="input" />
    </MarcoNodo>
  );
};

export default DescargarNodoNode;
