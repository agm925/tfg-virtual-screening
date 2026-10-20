import React, { useState, useEffect } from 'react';
import { Handle, Position } from 'reactflow';
import { apiFetch } from '../../api/client';
import MarcoNodo from './MarcoNodo';
import { seleccionInicial } from '../../utils/ficheros';
import { useIdioma } from '../../hooks/useIdioma';

// `tipo` lo verifica el backend contra el contenido real del fichero al
// subirlo (GET /moleculas), no es lo que declaró quien lo subió: antes el
// icono salía de si el fichero era privado o no, así que la molécula de
// entrada de una petición cualquiera --privada, pero una molécula corriente--
// se mostraba igual que una base de datos.
//
// Se agrupan con <optgroup> en vez de marcarlas con un emoji: un <option> no
// admite iconos SVG, y el grupo dice lo mismo con palabras.
const GRUPOS = [
  ['molecula',      'tabla.moleculas'],
  ['base_de_datos', 'moleculas.bibliotecas'],
  ['resultado',     'cabecera.resultados'],
];

const SelectMolNodoNode = ({ data, id }) => {
  const { t } = useIdioma();
  const [moleculas, setMoleculas] = useState([]);
  const [seleccionada, setSeleccionada] = useState(data.nombre_archivo || '');
  const [cargando, setCargando] = useState(true);
  const [falta, setFalta] = useState(false);   // el fichero guardado ya no existe
  const [error, setError] = useState(null);

  useEffect(() => { cargarMoleculas(); }, []);

  const cargarMoleculas = async () => {
    setCargando(true); setError(null);
    try {
      const resp = await apiFetch('/moleculas');
      if (!resp.ok) throw new Error();
      const lista = await resp.json();
      setMoleculas(lista);
      const inicial = seleccionInicial(data.nombre_archivo, lista);
      setSeleccionada(inicial.nombre);
      setFalta(inicial.falta);
      if (inicial.nombre) data.nombre_archivo = inicial.nombre;
    } catch { setError(t('nodos.error_moleculas')); }
    finally { setCargando(false); }
  };

  const handleCambio = (nombre) => { setSeleccionada(nombre); setFalta(false); data.nombre_archivo = nombre; };

  return (
    <MarcoNodo id={id} tipo="selectMol" data={data}>
      <div className="nodo-body">
        {cargando ? (
          <p className="nodo-nota">{t('nodos.cargando_moleculas')}</p>
        ) : error ? (
          <p className="nodo-aviso">{error}</p>
        ) : moleculas.length === 0 && !falta ? (
          <>
            <p className="nodo-aviso">{t('nodos.sin_moleculas')}</p>
            <p className="nodo-nota">{t('nodos.subela')}</p>
          </>
        ) : (
          <>
            <select className="select-input" value={seleccionada} onChange={e => handleCambio(e.target.value)}
                    aria-label={t('tabla.molecula')}>
              {falta && <option value={seleccionada}>{seleccionada} {t('nodos.ya_no_existe')}</option>}
              {GRUPOS.map(([tipo, titulo]) => {
                // Un tipo desconocido cae con las moléculas, como antes caía
                // en su icono.
                const delGrupo = moleculas.filter(m =>
                  (GRUPOS.some(([tipoGrupo]) => tipoGrupo === m.tipo) ? m.tipo : 'molecula') === tipo);
                return delGrupo.length > 0 && (
                  <optgroup key={tipo} label={t(titulo)}>
                    {delGrupo.map(m => (
                      <option key={m.nombre} value={m.nombre}>
                        {m.nombre}
                        {m.num_moleculas > 1
                          ? ` ${t('nodos.detalle_n', { n: m.num_moleculas, kb: m.tamano_kb })}`
                          : ` (${m.tamano_kb} KB)`}
                      </option>
                    ))}
                  </optgroup>
                );
              })}
            </select>
            {falta && <p className="nodo-aviso">{t('nodos.no_disponible')}</p>}
            <p className="nodo-nota">
              {t(moleculas.length === 1 ? 'nodos.un_fichero' : 'nodos.n_ficheros', { n: moleculas.length })} ·{' '}
              <button type="button" className="nodo-enlace" onClick={cargarMoleculas}>{t('nodos.actualizar')}</button>
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
