import React from 'react';
import { useReactFlow } from 'reactflow';
import { tipoNodo } from '../../utils/tiposNodo';
import '../../styles/Nodos.css';

// Lo comun a los nueve nodos: el marco con el color de su familia y la
// cabecera con su etiqueta y el boton de borrar. Antes cada nodo repetia la
// cabecera y su propio `eliminar`, y escribia a mano un nombre y un color que
// podian no coincidir con los de la paleta.
const MarcoNodo = ({ id, tipo, children }) => {
  const { setNodes, setEdges } = useReactFlow();
  const { etiqueta, familia } = tipoNodo(tipo);

  const eliminar = (e) => {
    e.stopPropagation();
    setNodes(nds => nds.filter(n => n.id !== id));
    setEdges(eds => eds.filter(ed => ed.source !== id && ed.target !== id));
  };

  return (
    <div className={`nodo familia-${familia}`}>
      <div className="nodo-header">
        {etiqueta}
        <button className="nodo-btn-borrar" onClick={eliminar}
                title="Eliminar nodo" aria-label={`Eliminar nodo ${etiqueta}`}>×</button>
      </div>
      {children}
    </div>
  );
};

export default MarcoNodo;
