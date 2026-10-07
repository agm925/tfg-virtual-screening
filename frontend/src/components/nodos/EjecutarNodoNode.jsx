import React from 'react';
import { Handle, Position } from 'reactflow';
import MarcoNodo from './MarcoNodo';

// Sin cuerpo propio: lo que hace ya lo dice la descripcion del marco.
const EjecutarNodoNode = ({ data, id }) => (
  <MarcoNodo id={id} tipo="ejecutar" data={data}>
    <Handle type="source" position={Position.Right} id="output" />
  </MarcoNodo>
);

export default EjecutarNodoNode;
