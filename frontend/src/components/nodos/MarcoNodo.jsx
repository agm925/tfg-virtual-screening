import React, { useContext } from 'react';
import { useReactFlow } from 'reactflow';
import { tipoNodo } from '../../utils/tiposNodo';
import Icono from '../Icono';
import { SoloLectura } from '../../utils/soloLectura';
import { useIdioma } from '../../hooks/useIdioma';
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
  const { t } = useIdioma();
  const tipoDelNodo = tipoNodo(tipo);
  const { familia, icono } = tipoDelNodo;
  const etiqueta = t(tipoDelNodo.etiqueta);
  const estado = data?.error ? 'error' : data?.ejecutado ? 'ejecutado' : '';
  const soloLectura = useContext(SoloLectura);

  const eliminar = (e) => {
    e.stopPropagation();
    setNodes(nds => nds.filter(n => n.id !== id));
    setEdges(eds => eds.filter(ed => ed.source !== id && ed.target !== id));
  };

  return (
    <div className={`nodo familia-${familia} ${estado}`}>
      <div className="nodo-header">
        <Icono nombre={icono} />{etiqueta}
        {!soloLectura && (
          <button className="nodo-btn-borrar" onClick={eliminar}
                  title={t('nodo.eliminar')} aria-label={t('nodo.eliminar_nombre', { nombre: etiqueta })}>
            <Icono nombre="cerrar" tamano={12} />
          </button>
        )}
      </div>
      {estado === 'ejecutado' && (
        <p className="nodo-estado ok" role="status"><Icono nombre="ok" tamano={14} />{t('nodo.terminado')}</p>
      )}
      {estado === 'error' && (
        <p className="nodo-estado error" role="status"><Icono nombre="error" tamano={14} />{t('nodo.ha_fallado')}</p>
      )}
      <p className="nodo-desc">{t(tipoDelNodo.descripcion)}</p>
      {/* En modo consulta (spec 012) el navegador desactiva todos los campos
          del nodo, también con el teclado, sin que cada nodo tenga que
          saberlo. */}
      <fieldset className="nodo-campos" disabled={soloLectura}>
        {children}
      </fieldset>
    </div>
  );
};

export default MarcoNodo;
