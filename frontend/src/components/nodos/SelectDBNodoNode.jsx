import React, { useState, useEffect } from 'react';
import { Handle, Position } from 'reactflow';
import { apiFetch } from '../../api/client';
import MarcoNodo from './MarcoNodo';

const SelectDBNodoNode = ({ data, id }) => {
  const [bases,       setBases]       = useState([]);
  const [seleccionada, setSeleccionada] = useState(data.nombre_archivo || '');
  const [cargando,    setCargando]    = useState(true);
  const [error,       setError]       = useState(null);

  useEffect(() => { cargarBases(); }, []);

  const cargarBases = async () => {
    setCargando(true); setError(null);
    try {
      const resp = await apiFetch('/moleculas');
      if (!resp.ok) throw new Error();
      const lista = await resp.json();
      // Consideramos BD todos los SDF (pueden tener 1 o miles de moléculas)
      const sdfs = lista.filter(m => m.nombre.toLowerCase().endsWith('.sdf'));
      setBases(sdfs);

      // Restaurar selección guardada o elegir la primera
      const guardada = sdfs.find(m => m.nombre === data.nombre_archivo);
      const elegida  = guardada || sdfs[0];
      if (elegida) aplicarCambio(elegida.nombre);
    } catch {
      setError('No se pudo cargar la lista de bases de datos');
    } finally {
      setCargando(false);
    }
  };

  const aplicarCambio = (nombre) => {
    setSeleccionada(nombre);
    data.nombre_archivo = nombre;
  };

  return (
    <MarcoNodo id={id} tipo="selectDB">
      <div className="nodo-body">
        {cargando ? (
          <p style={{ fontSize: '11px', color: '#7f8c8d', margin: 0 }}>Cargando bases de datos…</p>
        ) : error ? (
          <p style={{ fontSize: '11px', color: '#e74c3c', margin: 0 }}>{error}</p>
        ) : bases.length === 0 ? (
          <div>
            <p style={{ fontSize: '11px', color: '#e74c3c', margin: 0 }}>Sin bases de datos disponibles</p>
            <p style={{ fontSize: '10px', color: '#95a5a6', margin: '4px 0 0' }}>
              Sube un SDF desde la pestaña 🧪 Moléculas
            </p>
          </div>
        ) : (
          <>
            <select
              className="select-input"
              value={seleccionada}
              onChange={e => aplicarCambio(e.target.value)}
              style={{ width: '100%' }}
            >
              {bases.map(m => (
                <option key={m.nombre} value={m.nombre}>
                  📦 {m.nombre}
                  {m.num_moleculas != null ? ` (${m.num_moleculas} moléculas, ${m.tamano_kb} KB)` : ` (${m.tamano_kb} KB)`}
                </option>
              ))}
            </select>
            <p style={{ fontSize: '10px', color: '#7f8c8d', margin: 0 }}>
              {bases.length} base{bases.length !== 1 ? 's' : ''} disponible{bases.length !== 1 ? 's' : ''} ·{' '}
              <span
                style={{ color: '#9b59b6', cursor: 'pointer', textDecoration: 'underline' }}
                onClick={cargarBases}
              >
                actualizar
              </span>
            </p>
          </>
        )}
      </div>

      <Handle type="source" position={Position.Right} id="output" />
    </MarcoNodo>
  );
};

export default SelectDBNodoNode;
