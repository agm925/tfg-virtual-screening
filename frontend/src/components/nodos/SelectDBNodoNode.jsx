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
      setError('No se pudo cargar la lista de bibliotecas');
    } finally {
      setCargando(false);
    }
  };

  const aplicarCambio = (nombre) => {
    setSeleccionada(nombre);
    data.nombre_archivo = nombre;
  };

  return (
    <MarcoNodo id={id} tipo="selectDB" data={data}>
      <div className="nodo-body">
        {cargando ? (
          <p className="nodo-nota">Cargando bibliotecas…</p>
        ) : error ? (
          <p className="nodo-aviso">{error}</p>
        ) : bases.length === 0 ? (
          <>
            <p className="nodo-aviso">Todavía no tienes ninguna biblioteca.</p>
            <p className="nodo-nota">Sube un fichero SDF desde la página Moléculas.</p>
          </>
        ) : (
          <>
            <select
              className="select-input"
              value={seleccionada}
              onChange={e => aplicarCambio(e.target.value)}
              aria-label="Biblioteca"
            >
              {bases.map(m => (
                <option key={m.nombre} value={m.nombre}>
                  {m.nombre}
                  {m.num_moleculas != null ? ` (${m.num_moleculas} moléculas, ${m.tamano_kb} KB)` : ` (${m.tamano_kb} KB)`}
                </option>
              ))}
            </select>
            <p className="nodo-nota">
              {bases.length} biblioteca{bases.length !== 1 ? 's' : ''} ·{' '}
              <button type="button" className="nodo-enlace" onClick={cargarBases}>actualizar</button>
            </p>
          </>
        )}
      </div>

      <Handle type="source" position={Position.Right} id="output" />
    </MarcoNodo>
  );
};

export default SelectDBNodoNode;
