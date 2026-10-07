import React from 'react';
import { useReactFlow } from 'reactflow';
import { tipoNodo } from '../../utils/tiposNodo';
import Icono from '../Icono';
import '../../styles/Nodos.css';

// Lo comun a los nueve nodos: el marco con el color de su familia, la
// cabecera con su icono, su etiqueta y el boton de borrar, para que sirve el
// nodo y como acabo la ultima ejecucion. Antes cada nodo repetia la cabecera
// y su propio `eliminar`, y escribia a mano un nombre y un color que podian
// no coincidir con los de la paleta.
//
// `data.ejecutado` y `data.error` los rellena VisualBuilder al terminar una
// ejecucion; antes se rellenaban pero ningun nodo los miraba.
const MarcoNodo = ({ id, tipo, data, children }) => {
  const { setNodes, setEdges } = useReactFlow();
  const { etiqueta, familia, icono, descripcion } = tipoNodo(tipo);
  const estado = data?.error ? 'error' : data?.ejecutado ? 'ejecutado' : '';

  const eliminar = (e) => {
    e.stopPropagation();
    setNodes(nds => nds.filter(n => n.id !== id));
    setEdges(eds => eds.filter(ed => ed.source !== id && ed.target !== id));
  };

  return (
    <div className={`nodo familia-${familia} ${estado}`}>
      <div className="nodo-header">
        <Icono nombre={icono} />{etiqueta}
        <button className="nodo-btn-borrar" onClick={eliminar}
                title="Eliminar nodo" aria-label={`Eliminar nodo ${etiqueta}`}>
          <Icono nombre="cerrar" tamano={12} />
        </button>
      </div>
      {estado === 'ejecutado' && (
        <p className="nodo-estado ok" role="status"><Icono nombre="ok" tamano={14} />Terminado</p>
      )}
      {estado === 'error' && (
        <p className="nodo-estado error" role="status"><Icono nombre="error" tamano={14} />Ha fallado</p>
      )}
      <p className="nodo-desc">{descripcion}</p>
      {children}
    </div>
  );
};

export default MarcoNodo;
