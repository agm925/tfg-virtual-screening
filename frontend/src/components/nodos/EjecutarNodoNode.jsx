import React from 'react';
import { Handle, Position, useReactFlow } from 'reactflow';
import '../../styles/Nodos.css';

const EjecutarNodoNode = ({ data, id }) => {
  const { setNodes, setEdges } = useReactFlow();

  const eliminar = (e) => {
    e.stopPropagation();
    setNodes(nds => nds.filter(n => n.id !== id));
    setEdges(eds => eds.filter(e => e.source !== id && e.target !== id));
  };

  return (
    <div className="nodo ejecutar-nodo">
      <div className="nodo-header">
        ▶️ Ejecutar
        <button className="nodo-btn-borrar" onClick={eliminar} title="Eliminar nodo">×</button>
      </div>
      <div className="nodo-body">
        <p>Marca el inicio de ejecución del workflow</p>
      </div>
      <Handle type="source" position={Position.Right} id="output" />
    </div>
  );
};

export default EjecutarNodoNode;
