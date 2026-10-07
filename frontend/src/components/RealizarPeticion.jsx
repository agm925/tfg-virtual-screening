import { useState, useEffect, useRef } from 'react'
import { apiFetch, descargarConToken } from '../api/client'
import {
  claseEstado, textoEstado, estaActivo, etiquetaFichero, formatFecha,
} from '../utils/ficheros'
import { errorDeRespuesta, mensajeError } from '../utils/mensajes'
import VerEn3D from './VerEn3D'

const POLL_MS = 4000;

// ── Componente principal ─────────────────────────────────────────────────────

export default function RealizarPeticion({ usuario, abrirEnVisor }) {
  // — estado peticiones algoritmo —
  const [peticiones,   setPeticiones]   = useState([]);
  const [algoritmos,   setAlgoritmos]   = useState([]);
  const [archivo,      setArchivo]      = useState(null);
  const [algoritmoSel, setAlgoritmoSel] = useState('');
  const [mensaje,      setMensaje]      = useState(null); // { tipo: 'exito'|'error', texto }
  // Errores de las acciones de las tablas (cancelar, descargar): se enseñan
  // junto a las tablas, no arriba en el formulario, que puede quedar fuera
  // de la pantalla.
  const [avisoTablas,  setAvisoTablas]  = useState(null);
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
    const hayActivas = peticiones.some(p => estaActivo(p.estado));
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
    if (!archivo) {
      setMensaje({ tipo: 'error', texto: 'Elige una molécula en formato .mol2, .sdf o .mol.' });
      return;
    }
    setCargando(true); setMensaje(null);
    const fd = new FormData();
    fd.append('algoritmo_id', algoritmoSel);
    fd.append('archivo_mol',  archivo);

    const formulario = e.target;
    try {
      const resp = await apiFetch('/peticiones', { method: 'POST', body: fd });
      if (!resp.ok) throw await errorDeRespuesta(resp);
      setMensaje({ tipo: 'exito', texto: 'Petición enviada. Te avisaremos por correo cuando termine.' });
      setArchivo(null);
      formulario.reset();
      cargarDatos();
    } catch (err) {
      // Antes un fallo de red dejaba el boton en "Enviando…" para siempre.
      setMensaje({ tipo: 'error', texto: mensajeError('enviar la petición', err) });
    } finally {
      setCargando(false);
    }
  };

  // ── Cancelar ejecución de workflow ───────────────────────────────────────
  const cancelarEjecucion = async (id) => {
    if (!confirm('¿Cancelar esta ejecución? Se detendrá y no generará resultados.')) return;
    setAvisoTablas(null);
    try {
      const resp = await apiFetch(`/workflows/ejecuciones/${id}/cancelar`, { method: 'POST' });
      if (!resp.ok) throw await errorDeRespuesta(resp);
      cargarDatos();
    } catch (err) {
      setAvisoTablas(mensajeError('cancelar la ejecución', err));
    }
  };

  // ── Borrar petición ──────────────────────────────────────────────────────
  const borrarPeticion = async (id) => {
    if (!confirm('¿Borrar esta petición y su resultado?')) return;
    const resp = await apiFetch(`/peticiones/${id}`, { method: 'DELETE' });
    if (resp.ok) cargarDatos();
  };

  // ── Descargar resultado (endpoint autenticado: no puede ser un <a href> normal) ──
  const descargarPeticion = async (id, nombreSugerido) => {
    descargar(`/descargar/${id}`, nombreSugerido);
  };

  const descargar = async (ruta, nombre) => {
    setAvisoTablas(null);
    try {
      await descargarConToken(ruta, nombre);
    } catch (err) {
      setAvisoTablas(mensajeError('descargar el fichero', err));
    }
  };

  // ── Render ───────────────────────────────────────────────────────────────
  const hayActivas = peticiones.some(p => estaActivo(p.estado));

  return (
    <div className="seccion-wrapper">
      <h2>Resultados</h2>
      <p className="seccion-subtitulo">
        Tus peticiones de algoritmo y las ejecuciones de tus workflows, con los
        ficheros que generan. Solo los ves tú.
      </p>

      {/* ══════════ FORMULARIO NUEVA PETICIÓN ══════════ */}
      <section className="panel">
        <h3>Ejecutar un algoritmo sobre una molécula</h3>
        <form onSubmit={subirMolecula} className="formulario">
          <label htmlFor="peticion-algoritmo">Algoritmo</label>
          <select id="peticion-algoritmo" value={algoritmoSel}
                  onChange={e => setAlgoritmoSel(e.target.value)} required>
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
          <label htmlFor="peticion-molecula">Molécula (.mol2, .sdf o .mol)</label>
          <input id="peticion-molecula" type="file" accept=".mol2,.sdf,.mol"
                 onChange={e => setArchivo(e.target.files[0])} required />
          <button type="submit" className="btn-primary" disabled={cargando}>
            {cargando ? 'Enviando…' : 'Enviar a la cola'}
          </button>
        </form>
        {mensaje && (
          <p className={mensaje.tipo === 'exito' ? 'exito-msg' : 'error-msg'} role="status">
            {mensaje.texto}
          </p>
        )}
      </section>

      {avisoTablas && <p className="error-msg" role="status">{avisoTablas}</p>}

      {/* ══════════ TABLA PETICIONES DE ALGORITMO ══════════ */}
      <h3 className="subtitulo-tabla">
        Peticiones de algoritmo
        {hayActivas && <span className="aviso-vivo">Actualizando…</span>}
      </h3>

      <div className="tabla-contenedor">
        <table className="tabla-peticiones">
          <thead>
            <tr>
              <th>ID</th>
              <th>Fecha</th>
              <th>Algoritmo</th>
              <th>Molécula</th>
              <th>Estado</th>
              <th>Cola</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {peticiones.length === 0 && (
              <tr><td colSpan="7" className="tabla-vacia">
                Aún no has enviado ninguna petición. Usa el formulario de arriba.
              </td></tr>
            )}
            {peticiones.map(p => (
              <tr key={p.id}>
                <td className="col-id">#{p.id}</td>
                <td className="col-fecha">{formatFecha(p.fecha_creacion)}</td>
                <td>{p.algoritmo_nombre}</td>
                <td className="col-fichero">{p.ruta_mol_original}</td>
                <td>
                  <span className={`badge ${claseEstado(p.estado)}`}>{textoEstado(p.estado)}</span>
                </td>
                <td className="col-cifra">
                  {p.estado === 'PENDIENTE' && posiciones[p.id]
                    ? `Posición ${posiciones[p.id]}`
                    : p.estado === 'PROCESANDO' ? 'Ejecutando' : '—'}
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
                      className="btn-descarga"
                    >
                      Descargar resultado
                    </button>
                  )}
                  {p.estado === 'COMPLETADO' && p.ruta_mol_resultado && (
                    <VerEn3D fichero={p.ruta_mol_resultado} abrirEnVisor={abrirEnVisor} />
                  )}
                  <button onClick={() => borrarPeticion(p.id)} className="btn-borrar">Borrar</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ══════════ TABLA EJECUCIONES DE WORKFLOW ══════════ */}
      <h3 className="subtitulo-tabla">Ejecuciones de workflows</h3>
      <div className="tabla-contenedor">
        <table className="tabla-peticiones">
          <thead>
            <tr>
              <th>ID</th>
              <th>Fecha</th>
              <th>Workflow</th>
              <th>Estado</th>
              <th>Duración</th>
              <th>Ficheros</th>
            </tr>
          </thead>
          <tbody>
            {ejecuciones.length === 0 && (
              <tr><td colSpan="6" className="tabla-vacia">
                Aún no has ejecutado ningún workflow. Créalo en el Constructor.
              </td></tr>
            )}
            {ejecuciones.map(e => (
              <tr key={e.id}>
                <td className="col-id">#{e.id}</td>
                <td className="col-fecha">{formatFecha(e.fecha_ejecucion)}</td>
                <td>{e.workflow_nombre}</td>
                <td>
                  <span className={`badge ${claseEstado(e.estado)}`}>{textoEstado(e.estado)}</span>
                </td>
                <td className="col-cifra">
                  {e.duracion_segundos != null ? `${e.duracion_segundos} s` : '—'}
                </td>
                <td>
                  {e.archivos && e.archivos.length > 0 && e.archivos.map(f => (
                    <span key={f} className="fichero-acciones">
                      <button
                        onClick={() => descargar(`/uploads/${f}`, f)}
                        className="btn-descarga"
                        title={f}
                      >
                        {etiquetaFichero(f)}
                      </button>
                      <VerEn3D fichero={f} abrirEnVisor={abrirEnVisor} />
                    </span>
                  ))}
                  {estaActivo(e.estado) && (
                    <button onClick={() => cancelarEjecucion(e.id)} className="btn-borrar">
                      Cancelar ejecución
                    </button>
                  )}
                  {!e.archivos?.length && !estaActivo(e.estado) && <span className="col-cifra">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
