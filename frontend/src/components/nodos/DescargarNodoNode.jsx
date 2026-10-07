import React from 'react';
import { Handle, Position } from 'reactflow';
import MarcoNodo from './MarcoNodo';

// Sin cuerpo propio: lo que hace ya lo dice la descripcion del marco.
const DescargarNodoNode = ({ data, id }) => (
  <MarcoNodo id={id} tipo="descargar" data={data}>
    <Handle type="target" position={Position.Left} id="input" />
  </MarcoNodo>
);

export default DescargarNodoNode;
