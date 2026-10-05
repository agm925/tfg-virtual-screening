import React, { useState, useEffect } from 'react';
import { Handle, Position } from 'reactflow';
import { apiFetch } from '../../api/client';
import MarcoNodo from './MarcoNodo';

// `tipo` lo verifica el backend contra el contenido real del fichero al
// subirlo (GET /moleculas), no es lo que declaró quien lo subió: antes el
// icono salía de si el fichero era privado o no, así que la molécula de
// entrada de una petición cualquiera --privada, pero una molécula corriente--
// se mostraba igual que una base de datos.
const ICONO_TIPO = { molecula: '📁', base_de_datos: '🗄️', resultado: '📊' };

const SelectMolNodoNode = ({ data, id }) => {
  const [moleculas, setMoleculas] = useState([]);
  const [seleccionada, setSeleccionada] = useState(data.nombre_archivo || '');
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => { cargarMoleculas(); }, []);

  const cargarMoleculas = async () => {
    setCargando(true); setError(null);
    try {
      const resp = await apiFetch('/moleculas');
      if (!resp.ok) throw new Error();
      const lista = await resp.json();
      setMoleculas(lista);
      if (data.nombre_archivo && lista.find(m => m.nombre === data.nombre_archivo)) {
        setSeleccionada(data.nombre_archivo);
      } else if (lista.length > 0) {
        setSeleccionada(lista[0].nombre);
        data.nombre_archivo = lista[0].nombre;
      }
    } catch { setError('No se pudo cargar la lista de moléculas'); }
    finally { setCargando(false); }
  };

  const handleCambio = (nombre) => { setSeleccionada(nombre); data.nombre_archivo = nombre; };

  return (
    <MarcoNodo id={id} tipo="selectMol">
      <div className="nodo-body">
        {cargando ? (
          <p style={{ fontSize: '11px', color: '#7f8c8d', margin: 0 }}>Cargando moléculas...</p>
        ) : error ? (
          <p style={{ fontSize: '11px', color: '#e74c3c', margin: 0 }}>{error}</p>
        ) : moleculas.length === 0 ? (
          <p style={{ fontSize: '11px', color: '#e74c3c', margin: 0 }}>Sin moléculas disponibles</p>
        ) : (
          <>
            <select className="select-input" value={seleccionada} onChange={e => handleCambio(e.target.value)} style={{ width: '100%' }}>
              {moleculas.map(m => (
                <option key={m.nombre} value={m.nombre}>
                  {ICONO_TIPO[m.tipo] || '📁'} {m.nombre}
                  {m.num_moleculas > 1 ? ` (${m.num_moleculas} moléculas, ${m.tamano_kb} KB)` : ` (${m.tamano_kb} KB)`}
                </option>
              ))}
            </select>
            <p style={{ fontSize: '10px', color: '#7f8c8d', margin: '4px 0 0' }}>
              {moleculas.length} molécula{moleculas.length !== 1 ? 's' : ''} ·{' '}
              <span style={{ color: '#3498db', cursor: 'pointer', textDecoration: 'underline' }} onClick={cargarMoleculas}>
                actualizar
              </span>
            </p>
          </>
        )}
      </div>
      <Handle type="target" position={Position.Left}  id="input"  />
      <Handle type="source" position={Position.Right} id="output" />
    </MarcoNodo>
  );
};

export default SelectMolNodoNode;
