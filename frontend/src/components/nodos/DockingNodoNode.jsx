import React, { useState, useEffect } from 'react';
import { Handle, Position } from 'reactflow';
import { apiFetch } from '../../api/client';
import MarcoNodo from './MarcoNodo';

const DockingNodoNode = ({ data, id }) => {
  const [algoritmos, setAlgoritmos] = useState([]);
  const [seleccionado, setSeleccionado] = useState(String(data.algoritmo_id || ''));
  const [modoCaja, setModoCaja] = useState(data.modo_caja || 'auto');
  const [scoring, setScoring] = useState(data.scoring || 'vinardo');
  const [exhaustiveness, setExhaustiveness] = useState(data.exhaustiveness || 8);
  const [numModes, setNumModes] = useState(data.num_modes || 5);
  const [autoboxAdd, setAutoboxAdd] = useState(data.autobox_add || 8);
  const [caja, setCaja] = useState({
    center_x: data.center_x || 0, center_y: data.center_y || 0, center_z: data.center_z || 0,
    size_x: data.size_x || 20, size_y: data.size_y || 20, size_z: data.size_z || 20,
  });

  useEffect(() => {
    data.modo_caja = modoCaja;
    data.scoring = scoring;
    data.exhaustiveness = exhaustiveness;
    data.num_modes = numModes;
    data.autobox_add = autoboxAdd;
    Object.assign(data, caja);
  }, [modoCaja, scoring, exhaustiveness, numModes, autoboxAdd, caja]);

  useEffect(() => {
    cargarAlgoritmos();
  }, []);

  const cargarAlgoritmos = async () => {
    try {
      const todos = await apiFetch('/algoritmos').then(r => r.json());
      const filtrados = todos.filter(a => a.tipo === 'docking');
      setAlgoritmos(filtrados);
      if (filtrados.length === 0) return;
      const guardado = filtrados.find(a => String(a.id) === String(data.algoritmo_id));
      const elegido = guardado || filtrados[0];
      handleCambio(elegido.id, elegido.nombre, elegido.ruta_archivo);
    } catch (err) {
      console.error('Error cargando algoritmos de docking:', err);
    }
  };

  // algoritmo_ruta guarda el nombre real del .py; algoritmo_nombre es la
  // etiqueta que ve el usuario. El motor construye la ruta del script con
  // "algoritmo_ruta or algoritmo_nombre", asi que omitirlo aqui funcionaba
  // solo mientras ambos coincidian: en cuanto un algoritmo se registre como
  // "Docking con Smina" en vez de "dockingSmina", el flujo fallaria con
  // "Algoritmo no encontrado: algoritmos/Docking con Smina.py".
  const handleCambio = (id, nombre, rutaArchivo) => {
    setSeleccionado(String(id));
    data.algoritmo_id     = id;
    data.algoritmo_nombre = nombre;
    data.algoritmo_ruta   = rutaArchivo;
  };

  return (
    <MarcoNodo id={id} tipo="docking" data={data}>
      <div className="nodo-body">
        <select
          className="select-algo"
          aria-label="Algoritmo de docking"
          value={seleccionado}
          onChange={(e) => {
            const algo = algoritmos.find(a => String(a.id) === e.target.value);
            if (algo) handleCambio(algo.id, algo.nombre, algo.ruta_archivo);
          }}
        >
          {algoritmos.length > 0 ? (
            algoritmos.map(algo => (
              <option key={algo.id} value={String(algo.id)}>
                {algo.nombre}
              </option>
            ))
          ) : (
            <option disabled>Sin algoritmos de docking</option>
          )}
        </select>
        <p className="nodo-nota">
          Conecta el ligando al punto de la izquierda y el receptor al de abajo
          {modoCaja === 'referencia' && '; la referencia, al de arriba'}.
        </p>

        {/* Los nombres de smina (exhaustiveness, num_modes, autobox_add...)
            quedan en el tooltip para quien los conozca; la etiqueta visible
            dice en castellano para que sirve cada uno. */}
        <label className="nodo-campo">
          Función de puntuación
          <select className="select-input" value={scoring} onChange={(e) => setScoring(e.target.value)}>
            <option value="vinardo">Vinardo</option>
            <option value="vina">Vina</option>
            <option value="dkoes_fast">dkoes (rápida)</option>
            <option value="dkoes_scoring">dkoes</option>
          </select>
        </label>

        <div className="nodo-fila">
          <label className="nodo-campo" title="exhaustiveness: más alto, búsqueda más completa y más lenta">
            Exhaustividad
            <input type="number" className="select-input" value={exhaustiveness}
              min={1} max={32} onChange={(e) => setExhaustiveness(Number(e.target.value))} />
          </label>
          <label className="nodo-campo" title="num_modes: poses que se guardan por molécula">
            Poses
            <input type="number" className="select-input" value={numModes}
              min={1} max={20} onChange={(e) => setNumModes(Number(e.target.value))} />
          </label>
        </div>

        <label className="nodo-campo">
          Zona de búsqueda (caja)
          <select className="select-input" value={modoCaja} onChange={(e) => setModoCaja(e.target.value)}>
            <option value="auto">Alrededor del ligando (redocking)</option>
            <option value="referencia">Alrededor de una referencia</option>
            <option value="manual">Manual (centro y tamaño)</option>
          </select>
        </label>

        {modoCaja !== 'manual' && (
          <label className="nodo-campo" title="autobox_add">
            Margen alrededor (Å)
            <input type="number" className="select-input" value={autoboxAdd}
              onChange={(e) => setAutoboxAdd(Number(e.target.value))} />
          </label>
        )}

        {modoCaja === 'manual' && (
          <>
            <span className="nodo-campo">Centro (x, y, z), en Å</span>
            <div className="nodo-fila">
              {['center_x', 'center_y', 'center_z'].map((campo) => (
                <input key={campo} type="number" className="select-input"
                  value={caja[campo]} title={campo} aria-label={`Centro ${campo.slice(-1)}`}
                  onChange={(e) => setCaja({ ...caja, [campo]: Number(e.target.value) })} />
              ))}
            </div>
            <span className="nodo-campo">Tamaño (x, y, z), en Å</span>
            <div className="nodo-fila">
              {['size_x', 'size_y', 'size_z'].map((campo) => (
                <input key={campo} type="number" className="select-input"
                  value={caja[campo]} title={campo} aria-label={`Tamaño ${campo.slice(-1)}`}
                  onChange={(e) => setCaja({ ...caja, [campo]: Number(e.target.value) })} />
              ))}
            </div>
          </>
        )}
      </div>

      <Handle type="target" position={Position.Left}   id="input_ligando"  title="Ligando" style={{ top: '35%' }} />
      <Handle type="target" position={Position.Bottom} id="input_receptor" title="Receptor" />
      {/* Referencia cristalográfica: opcional, solo con la caja "referencia". */}
      {modoCaja === 'referencia' && (
        <Handle type="target" position={Position.Top} id="input_referencia" title="Referencia" />
      )}
      <Handle type="source" position={Position.Right}  id="output" title="Poses" />
    </MarcoNodo>
  );
};

export default DockingNodoNode;
