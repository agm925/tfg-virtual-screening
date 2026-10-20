import { useState, useEffect, useRef } from 'react'
import { apiFetch, descargarConToken } from '../api/client'
import {
  claseEstado, textoEstado, estaActivo, etiquetaFichero, formatFecha,
} from '../utils/ficheros'
import { errorDeRespuesta, mensajeError } from '../utils/mensajes'
import { ETIQUETA_ALGORITMO } from '../utils/tiposNodo'
import VerEn3D from './VerEn3D'
import Icono from './Icono'
import SelectorFichero from './SelectorFichero'
import { useIdioma } from '../hooks/useIdioma'

const POLL_MS = 4000;

// ── Componente principal ─────────────────────────────────────────────────────

export default function RealizarPeticion({ usuario, abrirEnVisor, verWorkflow }) {
  const { t, idioma } = useIdioma();
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
      setMensaje({ tipo: 'error', texto: t('resultados.elige_molecula') });
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
      setMensaje({ tipo: 'exito', texto: t('resultados.peticion_enviada') });
      setArchivo(null);
      formulario.reset();
      cargarDatos();
    } catch (err) {
      // Antes un fallo de red dejaba el boton en "Enviando…" para siempre.
      setMensaje({ tipo: 'error', texto: mensajeError(t('accion.enviar_peticion'), err, t) });
    } finally {
      setCargando(false);
    }
  };

  // ── Cancelar ejecución de workflow ───────────────────────────────────────
  const cancelarEjecucion = async (id) => {
    if (!confirm(t('resultados.confirmar_cancelar'))) return;
    setAvisoTablas(null);
    try {
      const resp = await apiFetch(`/workflows/ejecuciones/${id}/cancelar`, { method: 'POST' });
      if (!resp.ok) throw await errorDeRespuesta(resp);
      cargarDatos();
    } catch (err) {
      setAvisoTablas(mensajeError(t('accion.cancelar_ejecucion'), err, t));
    }
  };

  // ── Borrar los resultados de una ejecución (spec 012) ────────────────────
  const borrarEjecucion = async (id) => {
    if (!confirm(t('resultados.confirmar_borrar_ejecucion', { id }))) return;
    setAvisoTablas(null);
    try {
      const resp = await apiFetch(`/workflows/ejecuciones/${id}`, { method: 'DELETE' });
      if (!resp.ok) throw await errorDeRespuesta(resp);
      cargarDatos();
    } catch (err) {
      setAvisoTablas(mensajeError(t('accion.borrar_ejecucion'), err, t));
    }
  };

  // ── Borrar petición ──────────────────────────────────────────────────────
  const borrarPeticion = async (id) => {
    if (!confirm(t('resultados.confirmar_borrar_peticion'))) return;
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
      setAvisoTablas(mensajeError(t('accion.descargar_fichero'), err, t));
    }
  };

  // ── Render ───────────────────────────────────────────────────────────────
  const hayActivas = peticiones.some(p => estaActivo(p.estado));

  return (
    <div className="seccion-wrapper">
      <h2>{t('cabecera.resultados')}</h2>
      <p className="seccion-subtitulo">{t('resultados.subtitulo')}</p>

      {/* ══════════ FORMULARIO NUEVA PETICIÓN ══════════ */}
      <section className="panel">
        <h3>{t('resultados.ejecutar_titulo')}</h3>
        <form onSubmit={subirMolecula} className="formulario">
          <label htmlFor="peticion-algoritmo">{t('tabla.algoritmo')}</label>
          <select id="peticion-algoritmo" value={algoritmoSel}
                  onChange={e => setAlgoritmoSel(e.target.value)} required>
            {algoritmos.length === 0
              ? <option value="">{t('resultados.sin_algoritmos')}</option>
              : algoritmos.map(a => (
                  <option key={a.id} value={a.id}>{a.nombre} ({ETIQUETA_ALGORITMO[a.tipo] ? t(ETIQUETA_ALGORITMO[a.tipo]) : a.tipo})</option>
                ))}
          </select>
          {/* Los tres formatos que los algoritmos del catálogo saben leer
              (ver EXTENSIONES_ENTRADA_ALGORITMO en app/formatos.py). Antes
              solo se admitía .mol2, lo que obligaba a convertir cualquier
              SDF descargado de ChEMBL o PubChem -- y esa conversión degrada
              la química de muchos heterociclos aromáticos. */}
          <label htmlFor="peticion-molecula">{t('resultados.molecula_formatos')}</label>
          <SelectorFichero id="peticion-molecula" accept=".mol2,.sdf,.mol"
                           fichero={archivo} alElegir={setArchivo} />
          <button type="submit" className="btn-primary" disabled={cargando}>
            {cargando ? t('recordar.enviando') : t('resultados.enviar_cola')}
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
        {t('resultados.peticiones')}
        {hayActivas && <span className="aviso-vivo">{t('resultados.actualizando')}</span>}
      </h3>

      <div className="tabla-contenedor">
        <table className="tabla-peticiones">
          <thead>
            <tr>
              <th>{t('tabla.id')}</th>
              <th>{t('tabla.fecha')}</th>
              <th>{t('tabla.algoritmo')}</th>
              <th>{t('tabla.molecula')}</th>
              <th>{t('tabla.estado')}</th>
              <th>{t('tabla.cola')}</th>
              <th>{t('tabla.acciones')}</th>
            </tr>
          </thead>
          <tbody>
            {peticiones.length === 0 && (
              <tr><td colSpan="7" className="tabla-vacia">
                {t('resultados.sin_peticiones')}
              </td></tr>
            )}
            {peticiones.map(p => (
              <tr key={p.id}>
                <td data-label={t('tabla.id')} className="col-id">#{p.id}</td>
                <td data-label={t('tabla.fecha')} className="col-fecha">{formatFecha(p.fecha_creacion, idioma)}</td>
                <td data-label={t('tabla.algoritmo')}>{p.algoritmo_nombre}</td>
                <td data-label={t('tabla.molecula')} className="col-fichero">{p.ruta_mol_original}</td>
                <td data-label={t('tabla.estado')}>
                  <span className={`badge ${claseEstado(p.estado)}`}>{textoEstado(p.estado, t)}</span>
                </td>
                <td data-label={t('tabla.cola')} className="col-cifra">
                  {p.estado === 'PENDIENTE' && posiciones[p.id]
                    ? t('resultados.posicion', { n: posiciones[p.id] })
                    : p.estado === 'PROCESANDO' ? t('resultados.ejecutando') : '—'}
                </td>
                <td data-label={t('tabla.acciones')} className="acciones-celda">
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
                      {t('resultados.descargar_resultado')}
                    </button>
                  )}
                  {p.estado === 'COMPLETADO' && p.ruta_mol_resultado && (
                    <VerEn3D fichero={p.ruta_mol_resultado} abrirEnVisor={abrirEnVisor} />
                  )}
                  <button onClick={() => borrarPeticion(p.id)} className="btn-borrar">{t('comun.borrar')}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ══════════ TABLA EJECUCIONES DE WORKFLOW ══════════ */}
      <h3 className="subtitulo-tabla">{t('resultados.ejecuciones')}</h3>
      <div className="tabla-contenedor">
        <table className="tabla-peticiones">
          <thead>
            <tr>
              <th>{t('tabla.id')}</th>
              <th>{t('tabla.fecha')}</th>
              <th>{t('tabla.workflow')}</th>
              <th>{t('tabla.estado')}</th>
              <th>{t('tabla.duracion')}</th>
              <th>{t('tabla.ficheros')}</th>
              <th>{t('tabla.acciones')}</th>
            </tr>
          </thead>
          <tbody>
            {ejecuciones.length === 0 && (
              <tr><td colSpan="7" className="tabla-vacia">
                {t('resultados.sin_ejecuciones')}
              </td></tr>
            )}
            {ejecuciones.map(e => (
              <tr key={e.id}>
                <td data-label={t('tabla.id')} className="col-id">#{e.id}</td>
                <td data-label={t('tabla.fecha')} className="col-fecha">{formatFecha(e.fecha_ejecucion, idioma)}</td>
                <td data-label={t('tabla.workflow')}>
                  {e.workflow_nombre}
                  {e.workflow_borrado && <span className="texto-secundario"> {t('resultados.borrado')}</span>}
                </td>
                <td data-label={t('tabla.estado')}>
                  <span className={`badge ${claseEstado(e.estado)}`}>{textoEstado(e.estado, t)}</span>
                </td>
                <td data-label={t('tabla.duracion')} className="col-cifra">
                  {e.duracion_segundos != null ? `${e.duracion_segundos} s` : '—'}
                </td>
                <td data-label={t('tabla.ficheros')}>
                  {e.archivos && e.archivos.length > 0 && e.archivos.map(f => (
                    <span key={f} className="fichero-acciones">
                      <button
                        onClick={() => descargar(`/uploads/${f}`, f)}
                        className="btn-descarga"
                        title={f}
                      >
                        {etiquetaFichero(f, t)}
                      </button>
                      <VerEn3D fichero={f} abrirEnVisor={abrirEnVisor} />
                    </span>
                  ))}
                  {!e.archivos?.length && <span className="col-cifra">—</span>}
                </td>
                <td data-label={t('tabla.acciones')}>
                  <span className="acciones-ejecucion">
                    <button onClick={() => verWorkflow(e)} className="btn-descarga">
                      <Icono nombre="nodos" />{t('resultados.ver_workflow')}
                    </button>
                    {/* En marcha no se puede borrar (el backend responde 409):
                        primero se cancela. */}
                    {estaActivo(e.estado) ? (
                      <button onClick={() => cancelarEjecucion(e.id)} className="btn-borrar">
                        {t('resultados.cancelar_ejecucion')}
                      </button>
                    ) : (
                      <button onClick={() => borrarEjecucion(e.id)} className="btn-borrar">
                        <Icono nombre="papelera" />{t('comun.borrar')}
                      </button>
                    )}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
