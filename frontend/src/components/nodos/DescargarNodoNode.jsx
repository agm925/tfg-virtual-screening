import React from 'react';
import { Handle, Position, useReactFlow } from 'reactflow';
import '../../styles/Nodos.css';

const DescargarNodoNode = ({ data, id }) => {
  const { setNodes, setEdges } = useReactFlow();

  const eliminar = (e) => {
    e.stopPropagation();
    setNodes(nds => nds.filter(n => n.id !== id));
    setEdges(eds => eds.filter(e => e.source !== id && e.target !== id));
  };

  return (
    <div className="nodo descargar-nodo">
      <div className="nodo-header">
        📥 Descargar
        <button className="nodo-btn-borrar" onClick={eliminar} title="Eliminar nodo">×</button>
      </div>
      <div className="nodo-body">
        <p>Archivo listo para descargar</p>
      </div>
      <Handle type="target" position={Position.Left} id="input" />
    </div>
  );
};

export default DescargarNodoNode;
