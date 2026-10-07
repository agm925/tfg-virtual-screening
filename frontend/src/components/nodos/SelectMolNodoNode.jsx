import React, { useState, useEffect } from 'react';
import { Handle, Position } from 'reactflow';
import { apiFetch } from '../../api/client';
import MarcoNodo from './MarcoNodo';

// `tipo` lo verifica el backend contra el contenido real del fichero al
// subirlo (GET /moleculas), no es lo que declaró quien lo subió: antes el
// icono salía de si el fichero era privado o no, así que la molécula de
// entrada de una petición cualquiera --privada, pero una molécula corriente--
// se mostraba igual que una base de datos.
//
// Se agrupan con <optgroup> en vez de marcarlas con un emoji: un <option> no
// admite iconos SVG, y el grupo dice lo mismo con palabras.
const GRUPOS = [
  ['molecula',      'Moléculas'],
  ['base_de_datos', 'Bibliotecas'],
  ['resultado',     'Resultados'],
];

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
    <MarcoNodo id={id} tipo="selectMol" data={data}>
      <div className="nodo-body">
        {cargando ? (
          <p className="nodo-nota">Cargando moléculas…</p>
        ) : error ? (
          <p className="nodo-aviso">{error}</p>
        ) : moleculas.length === 0 ? (
          <>
            <p className="nodo-aviso">Todavía no tienes ninguna molécula.</p>
            <p className="nodo-nota">Súbela desde la página Moléculas o con el nodo Subir molécula.</p>
          </>
        ) : (
          <>
            <select className="select-input" value={seleccionada} onChange={e => handleCambio(e.target.value)}
                    aria-label="Molécula">
              {GRUPOS.map(([tipo, titulo]) => {
                // Un tipo desconocido cae con las moléculas, como antes caía
                // en su icono.
                const delGrupo = moleculas.filter(m =>
                  (GRUPOS.some(([t]) => t === m.tipo) ? m.tipo : 'molecula') === tipo);
                return delGrupo.length > 0 && (
                  <optgroup key={tipo} label={titulo}>
                    {delGrupo.map(m => (
                      <option key={m.nombre} value={m.nombre}>
                        {m.nombre}
                        {m.num_moleculas > 1 ? ` (${m.num_moleculas} moléculas, ${m.tamano_kb} KB)` : ` (${m.tamano_kb} KB)`}
                      </option>
                    ))}
                  </optgroup>
                );
              })}
            </select>
            <p className="nodo-nota">
              {moleculas.length} fichero{moleculas.length !== 1 ? 's' : ''} ·{' '}
              <button type="button" className="nodo-enlace" onClick={cargarMoleculas}>actualizar</button>
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
