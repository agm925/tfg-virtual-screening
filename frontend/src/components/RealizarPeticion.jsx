import { useState, useEffect, useRef } from 'react'
import { apiFetch, descargarConToken } from '../api/client'

const POLL_MS = 4000;

// ── Utilidades ───────────────────────────────────────────────────────────────

const BADGE_CLASE  = { PENDIENTE:'pendiente', PROCESANDO:'procesando', COMPLETADO:'completado', ERROR:'error', cancelado:'cancelado',
                       pendiente:'pendiente',  procesando:'procesando',  completado:'completado', error:'error' };
const BADGE_LABEL  = { PENDIENTE:'⏳ En cola', PROCESANDO:'⚙️ Procesando', COMPLETADO:'✅ Completado', ERROR:'❌ Error', cancelado:'🚫 Cancelado',
                       pendiente:'⏳ En cola',  procesando:'⚙️ Procesando',  completado:'✅ Completado', error:'❌ Error' };

const CANCELABLE = ['pendiente', 'procesando', 'PENDIENTE', 'PROCESANDO'];

function formatFecha(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('es-ES', { day:'2-digit', month:'2-digit', year:'numeric' })
    + ' ' + d.toLocaleTimeString('es-ES', { hour:'2-digit', minute:'2-digit' });
}

// ── Componente principal ─────────────────────────────────────────────────────

export default function RealizarPeticion({ usuario }) {
  // — estado peticiones algoritmo —
  const [peticiones,   setPeticiones]   = useState([]);
  const [algoritmos,   setAlgoritmos]   = useState([]);
  const [archivo,      setArchivo]      = useState(null);
  const [algoritmoSel, setAlgoritmoSel] = useState('');
  const [mensaje,      setMensaje]      = useState('');
  const [cargando,     setCargando]     = useState(false);
  const [posiciones,   setPosiciones]   = useState({});
  const intervalRef = useRef(null);

  // — estado ejecuciones workflow —
  const [ejecuciones, setEjecuciones] = useState([]);

  // ── Carga inicial ────────────────────────────────────────────────────────
  const cargarDatos = async () => {
    const [rPet, rAlg, rEjec] = await Promise.all([
      apiFetch(`/peticiones/usuario/${usuario.id}`),
      apiFetch(`/algoritmos`),
      apiFetch(`/ejecuciones/usuario/${usuario.id}`),
    ]);
    if (rPet.ok)  setPeticiones(await rPet.json());
    if (rEjec.ok) setEjecuciones(await rEjec.json());
    if (rAlg.ok) {
      const data = await rAlg.json();
      setAlgoritmos(data);
      if (data.length > 0 && !algoritmoSel) setAlgoritmoSel(data[0].id);
    }
  };

  // ── Polling peticiones activas ───────────────────────────────────────────
  const pollEstados = async (lista) => {
    const activas = lista.filter(p => ['PENDIENTE','PROCESANDO'].includes(p.estado));
    if (!activas.length) return;

    const estados = await Promise.all(
      activas.map(p =>
        apiFetch(`/peticiones/${p.id}/estado`).then(r => r.json())
      )
    );

    const nuevasPos = {};
    let cambio = false;
    setPeticiones(prev => prev.map(p => {
      const nuevo = estados.find(e => e.id === p.id);
      if (!nuevo) return p;
      if (nuevo.posicion_en_cola) nuevasPos[p.id] = nuevo.posicion_en_cola;
      if (nuevo.estado !== p.estado) cambio = true;
      return { ...p, estado: nuevo.estado };
    }));
    setPosiciones(nuevasPos);
    if (cambio) cargarDatos();
  };

  useEffect(() => { cargarDatos(); }, []);

  useEffect(() => {
    const hayActivas = peticiones.some(p => ['PENDIENTE','PROCESANDO'].includes(p.estado));
    if (hayActivas) {
      if (!intervalRef.current)
        intervalRef.current = setInterval(() => pollEstados(peticiones), POLL_MS);
    } else {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    return () => { clearInterval(intervalRef.current); intervalRef.current = null; };
  }, [peticiones]);

  // ── Crear petición ───────────────────────────────────────────────────────
  const subirMolecula = async (e) => {
    e.preventDefault();
    if (!archivo) { setMensaje('Selecciona un archivo de molécula (.mol2, .sdf o .mol)'); return; }
    setCargando(true); setMensaje('');
    const fd = new FormData();
    fd.append('algoritmo_id', algoritmoSel);
    fd.append('archivo_mol',  archivo);

    const resp = await apiFetch('/peticiones', { method: 'POST', body: fd });
    setCargando(false);
    if (resp.ok) {
      setMensaje('✅ Petición enviada — recibirás un correo al terminar.');
      setArchivo(null);
      e.target.reset();
      cargarDatos();
    } else {
      const err = await resp.json();
      setMensaje(`❌ Error: ${err.detail || 'No se pudo crear la petición'}`);
    }
  };

  // ── Cancelar ejecución de workflow ───────────────────────────────────────
  const cancelarEjecucion = async (id) => {
    if (!confirm('¿Cancelar esta ejecución? El proceso se detendrá.')) return;
    const resp = await apiFetch(`/workflows/ejecuciones/${id}/cancelar`, { method: 'POST' });
    if (resp.ok) cargarDatos();
    else {
      const err = await resp.json();
      alert(err.detail || 'No se pudo cancelar');
    }
  };

  // ── Borrar petición ──────────────────────────────────────────────────────
  const borrarPeticion = async (id) => {
    if (!confirm('¿Eliminar esta petición?')) return;
    const resp = await apiFetch(`/peticiones/${id}`, { method: 'DELETE' });
    if (resp.ok) cargarDatos();
  };

  // ── Descargar resultado (endpoint autenticado: no puede ser un <a href> normal) ──
  const descargarPeticion = async (id, nombreSugerido) => {
    try {
      await descargarConToken(`/descargar/${id}`, nombreSugerido);
    } catch (e) {
      alert(e.message);
    }
  };

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="seccion-wrapper">
      <h2>Peticiones</h2>
      <p style={{ color:'#666', marginBottom:'24px', fontSize:'14px' }}>
        Aquí aparecen tanto las peticiones directas de algoritmos como las ejecuciones
        de tus workflows del Constructor Visual, todas privadas y solo visibles para ti.
      </p>

      {/* ══════════ FORMULARIO NUEVA PETICIÓN ══════════ */}
      <div style={{ background:'white', borderRadius:'12px', padding:'24px',
                    boxShadow:'0 2px 10px rgba(0,0,0,0.07)', marginBottom:'36px' }}>
        <h3 style={{ margin:'0 0 16px', color:'#2c3e50' }}>📤 Nueva petición de algoritmo</h3>
        <form onSubmit={subirMolecula} className="formulario">
          <label>Algoritmo a ejecutar</label>
          <select value={algoritmoSel} onChange={e => setAlgoritmoSel(e.target.value)} required>
            {algoritmos.length === 0
              ? <option value="">No hay algoritmos disponibles</option>
              : algoritmos.map(a => (
                  <option key={a.id} value={a.id}>{a.nombre} ({a.tipo})</option>
                ))}
          </select>
          {/* Los tres formatos que los algoritmos del catálogo saben leer
              (ver EXTENSIONES_ENTRADA_ALGORITMO en app/formatos.py). Antes
              solo se admitía .mol2, lo que obligaba a convertir cualquier
              SDF descargado de ChEMBL o PubChem -- y esa conversión degrada
              la química de muchos heterociclos aromáticos. */}
          <label>Molécula (.mol2, .sdf o .mol)</label>
          <input type="file" accept=".mol2,.sdf,.mol" onChange={e => setArchivo(e.target.files[0])} required />
          <button type="submit" className="btn-primary verde" disabled={cargando}>
            {cargando ? '⏳ Enviando...' : '📤 Enviar a la cola'}
          </button>
        </form>
        {mensaje && (
          <p className={mensaje.startsWith('✅') ? 'exito-msg' : 'error-msg'}>{mensaje}</p>
        )}
      </div>

      {/* ══════════ TABLA PETICIONES DE ALGORITMO ══════════ */}
      <h3 style={{ color:'#2c3e50', marginBottom:'12px' }}>
        🔬 Peticiones de algoritmo
        {peticiones.some(p => ['PENDIENTE','PROCESANDO'].includes(p.estado)) && (
          <span style={{ fontSize:'13px', color:'#888', fontWeight:'normal', marginLeft:'10px' }}>
            🔄 actualizando…
          </span>
        )}
      </h3>

      <table className="tabla-peticiones" style={{ marginBottom:'40px' }}>
        <thead>
          <tr>
            <th>ID</th>
            <th>Fecha</th>
            <th>Algoritmo</th>
            <th>Archivo entrada</th>
            <th>Estado</th>
            <th>Cola</th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          {peticiones.length === 0 && (
            <tr><td colSpan="7" className="tabla-vacia">No hay peticiones todavía</td></tr>
          )}
          {peticiones.map(p => (
            <tr key={p.id}>
              <td>#{p.id}</td>
              <td style={{ fontSize:'12px', whiteSpace:'nowrap' }}>{formatFecha(p.fecha_creacion)}</td>
              <td style={{ fontSize:'12px' }}>{p.algoritmo_nombre}</td>
              <td style={{ fontSize:'12px' }}>{p.ruta_mol_original}</td>
              <td>
                <span className={`badge ${BADGE_CLASE[p.estado] || 'pendiente'}`}>
                  {BADGE_LABEL[p.estado] || p.estado}
                </span>
              </td>
              <td style={{ fontSize:'12px', color:'#888' }}>
                {p.estado === 'PENDIENTE' && posiciones[p.id]
                  ? `Posición ${posiciones[p.id]}`
                  : p.estado === 'PROCESANDO' ? '⚙️ ejecutando' : '—'}
              </td>
              <td className="acciones-celda">
                {p.estado === 'COMPLETADO' && (
                  /* El nombre sugerido es el del RESULTADO, no el de la entrada.
                     descargarConToken hace a.download = nombreSugerido, que pisa
                     el nombre que manda el servidor: con el de la entrada, un
                     resultado JSON --un filtro, una comparacion, un RMSD-- se
                     descargaba llamandose .sdf. El backend renombra esos
                     ficheros a proposito (corregir_extension en app/tasks.py)
                     para que no se hagan pasar por moleculas, y esto lo
                     deshacia en el ultimo paso. */
                  <button
                    onClick={() => descargarPeticion(p.id, p.ruta_mol_resultado || p.ruta_mol_original)}
                    className="btn-ejecutar"
                  >
                    📥 Descargar
                  </button>
                )}
                <button onClick={() => borrarPeticion(p.id)} className="btn-borrar">Borrar</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* ══════════ TABLA EJECUCIONES DE WORKFLOW ══════════ */}
      <h3 style={{ color:'#2c3e50', marginBottom:'12px' }}>🔧 Ejecuciones de workflows</h3>
      <table className="tabla-peticiones">
        <thead>
          <tr>
            <th>ID</th>
            <th>Fecha</th>
            <th>Workflow</th>
            <th>Estado</th>
            <th>Duración</th>
            <th>Archivos generados</th>
          </tr>
        </thead>
        <tbody>
          {ejecuciones.length === 0 && (
            <tr><td colSpan="6" className="tabla-vacia">No hay ejecuciones de workflow todavía</td></tr>
          )}
          {ejecuciones.map(e => (
            <tr key={e.id}>
              <td>#{e.id}</td>
              <td style={{ fontSize:'12px', whiteSpace:'nowrap' }}>{formatFecha(e.fecha_ejecucion)}</td>
              <td style={{ fontSize:'12px' }}>{e.workflow_nombre}</td>
              <td>
                <span className={`badge ${BADGE_CLASE[e.estado] || 'pendiente'}`}>
                  {BADGE_LABEL[e.estado] || e.estado}
                </span>
              </td>
              <td style={{ fontSize:'12px', color:'#888' }}>
                {e.duracion_segundos != null ? `${e.duracion_segundos}s` : '—'}
              </td>
              <td>
                {e.archivos && e.archivos.length > 0
                  ? e.archivos.map(f => (
                      <button
                        key={f}
                        onClick={() => descargarConToken(`/uploads/${f}`, f).catch(err => alert(err.message))}
                        className="btn-ejecutar"
                        style={{ display:'inline-block',
                                 marginRight:'6px', marginBottom:'4px', fontSize:'11px' }}
                      >
                        📥 {f}
                      </button>
                    ))
                  : <span style={{ fontSize:'12px', color:'#aaa' }}>—</span>
                }
                {CANCELABLE.includes(e.estado) && (
                  <button
                    onClick={() => cancelarEjecucion(e.id)}
                    style={{ fontSize:'11px', padding:'3px 8px', marginLeft:'4px',
                             background:'#e74c3c', color:'white', border:'none',
                             borderRadius:'4px', cursor:'pointer' }}
                  >
                    🚫 Cancelar
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
