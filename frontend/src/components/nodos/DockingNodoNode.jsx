import React, { useState, useEffect } from 'react';
import { Handle, Position, useReactFlow } from 'reactflow';
import '../../styles/Nodos.css';

const DockingNodoNode = ({ data, id }) => {
  const { setNodes, setEdges } = useReactFlow();
  const eliminar = (e) => {
    e.stopPropagation();
    setNodes(nds => nds.filter(n => n.id !== id));
    setEdges(eds => eds.filter(e => e.source !== id && e.target !== id));
  };
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
      const todos = await fetch('http://localhost:8000/algoritmos').then(r => r.json());
      const filtrados = todos.filter(a => a.tipo === 'docking');
      setAlgoritmos(filtrados);
      if (filtrados.length === 0) return;
      const guardado = filtrados.find(a => String(a.id) === String(data.algoritmo_id));
      const elegido = guardado || filtrados[0];
      handleCambio(elegido.id, elegido.nombre);
    } catch (err) {
      console.error('Error cargando algoritmos de docking:', err);
    }
  };

  const handleCambio = (id, nombre) => {
    setSeleccionado(String(id));
    data.algoritmo_id     = id;
    data.algoritmo_nombre = nombre;
  };

  return (
    <div className="nodo docking-nodo">
      <div className="nodo-header">
        🔬 Docking
        <button className="nodo-btn-borrar" onClick={eliminar} title="Eliminar nodo">×</button>
      </div>

      <div className="nodo-body">
        <select
          className="select-algo"
          value={seleccionado}
          onChange={(e) => {
            const algo = algoritmos.find(a => String(a.id) === e.target.value);
            if (algo) handleCambio(algo.id, algo.nombre);
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
        <p className="algo-desc" style={{ fontSize: '0.7rem' }}>
          Ligando → <strong>input_ligando</strong> (izq.)<br />
          Receptor → <strong>input_receptor</strong> (inf.)
        </p>

        <select className="select-input" value={scoring} onChange={(e) => setScoring(e.target.value)}>
          <option value="vinardo">Scoring: vinardo</option>
          <option value="vina">Scoring: vina</option>
          <option value="dkoes_fast">Scoring: dkoes_fast</option>
          <option value="dkoes_scoring">Scoring: dkoes_scoring</option>
        </select>

        <div style={{ display: 'flex', gap: '4px' }}>
          <input type="number" className="select-input" style={{ width: '50%' }} value={exhaustiveness}
            min={1} max={32} title="exhaustiveness" onChange={(e) => setExhaustiveness(Number(e.target.value))} />
          <input type="number" className="select-input" style={{ width: '50%' }} value={numModes}
            min={1} max={20} title="num_modes" onChange={(e) => setNumModes(Number(e.target.value))} />
        </div>

        <select className="select-input" value={modoCaja} onChange={(e) => setModoCaja(e.target.value)}>
          <option value="auto">Caja: autobox sobre el ligando (redocking)</option>
          <option value="referencia">Caja: autobox sobre referencia</option>
          <option value="manual">Caja: manual (centro + tamaño)</option>
        </select>

        {modoCaja !== 'manual' && (
          <input type="number" className="select-input" value={autoboxAdd} title="autobox_add"
            placeholder="autobox_add (Å)" onChange={(e) => setAutoboxAdd(Number(e.target.value))} />
        )}

        {modoCaja === 'manual' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <div style={{ display: 'flex', gap: '4px' }}>
              {['center_x', 'center_y', 'center_z'].map((campo) => (
                <input key={campo} type="number" className="select-input" style={{ width: '33%' }}
                  value={caja[campo]} title={campo} placeholder={campo}
                  onChange={(e) => setCaja({ ...caja, [campo]: Number(e.target.value) })} />
              ))}
            </div>
            <div style={{ display: 'flex', gap: '4px' }}>
              {['size_x', 'size_y', 'size_z'].map((campo) => (
                <input key={campo} type="number" className="select-input" style={{ width: '33%' }}
                  value={caja[campo]} title={campo} placeholder={campo}
                  onChange={(e) => setCaja({ ...caja, [campo]: Number(e.target.value) })} />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Entrada ligando (izquierda) */}
      <Handle type="target" position={Position.Left}   id="input_ligando"  style={{ top: '35%' }} />
      {/* Entrada receptor (abajo) */}
      <Handle type="target" position={Position.Bottom} id="input_receptor" />
      {/* Entrada referencia cristalográfica (opcional, solo modo "referencia") */}
      {modoCaja === 'referencia' && (
        <Handle type="target" position={Position.Top} id="input_referencia" />
      )}
      {/* Salida poses */}
      <Handle type="source" position={Position.Right}  id="output" />
    </div>
  );
};

export default DockingNodoNode;
