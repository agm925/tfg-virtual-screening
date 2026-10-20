import React, { useContext, useEffect, useState } from 'react';
import { Handle, Position, useReactFlow, useUpdateNodeInternals } from 'reactflow';
import { conectoresDe, conexionesSobrantes } from '../../utils/interfaz';
import { SoloLectura } from '../../utils/soloLectura';

// Los conectores y las opciones de un algoritmo con interfaz declarada
// (spec 013), comunes a los cuatro nodos de algoritmo: un conector con nombre
// por entrada, en el orden en que el motor se las pasa al script
// (entrada_0..N-1), y una casilla por opción de sí/no. Sin interfaz no pinta
// nada y el nodo pone sus conectores de siempre (`idsDeSiempre`).
//
// Al cambiar de algoritmo cambian los conectores: React Flow no los recoloca
// si no se le avisa (useUpdateNodeInternals), y las conexiones a uno que ya no
// existe quedarían colgando de un punto que no se ve. Se quitan solo cuando la
// lista de algoritmos ya ha llegado (`listo`): antes, el nodo aún no sabe qué
// algoritmo tiene, y abrir un workflow guardado le borraría sus conexiones. En
// modo consulta (spec 012) no se toca nada.
export default function ConectoresInterfaz({ id, data, interfaz, idsDeSiempre, listo }) {
  const { getEdges, setEdges, setNodes } = useReactFlow();
  const recolocarConectores = useUpdateNodeInternals();
  const soloLectura = useContext(SoloLectura);
  const [marcadas, setMarcadas] = useState(data.opciones_marcadas || []);

  const conectores = conectoresDe(interfaz);
  const ids = conectores ? conectores.map(c => c.id) : idsDeSiempre;
  const claveConectores = ids.join(',');

  useEffect(() => {
    recolocarConectores(id);
    if (!listo || soloLectura) return;
    // Por id: getEdges devuelve copias, no las aristas del estado.
    const sobran = new Set(conexionesSobrantes(getEdges(), id, ids).map(a => a.id));
    if (sobran.size) setEdges(aristas => aristas.filter(a => !sobran.has(a.id)));
    // Solo cuando cambian los conectores o termina de cargar la lista.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [claveConectores, listo]);

  if (!conectores) return null;

  // Se guarda en el nodo con setNodes, sin escribir sobre `data`. El motor solo
  // pasa al script las que declara la interfaz, así que una que sobre de un
  // algoritmo anterior no llega a la llamada.
  const alternar = (opcion, marcada) => {
    const nuevas = marcada ? [...marcadas, opcion] : marcadas.filter(o => o !== opcion);
    setMarcadas(nuevas);
    setNodes(nodos => nodos.map(n => (n.id === id
      ? { ...n, data: { ...n.data, opciones_marcadas: nuevas } }
      : n)));
  };

  return (
    <>
      <div className="nodo-entradas">
        {conectores.map(c => (
          <div className="nodo-entrada" key={c.id}>
            <Handle type="target" position={Position.Left} id={c.id} title={c.nombre} />
            {c.nombre}
          </div>
        ))}
      </div>
      {interfaz.opciones?.length > 0 && (
        <div className="opciones-checkbox">
          {interfaz.opciones.map(o => (
            <label key={o.opcion} title={o.opcion}>
              <input type="checkbox" checked={marcadas.includes(o.opcion)}
                     onChange={e => alternar(o.opcion, e.target.checked)} />
              {o.nombre}
            </label>
          ))}
        </div>
      )}
    </>
  );
}
