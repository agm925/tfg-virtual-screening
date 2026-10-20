import { useEffect, useState } from 'react'
import { apiFetch, descargarConToken } from '../api/client'
import { claseEstado, textoEstado, etiquetaFichero, formatFecha } from '../utils/ficheros'
import { mensajeError } from '../utils/mensajes'
import VerEn3D from './VerEn3D'
import Icono from './Icono'
import { useIdioma } from '../hooks/useIdioma'

// Cuántas ejecuciones recientes se enseñan aquí; el resto está en Resultados.
const RECIENTES = 5;

// Inicio es el banco de trabajo: lo que el usuario puede hacer ahora y lo
// último que ha lanzado, con sus ficheros a mano. Antes eran cuatro tarjetas
// de presentación iguales para todos, y los resultados de un cribado no
// aparecían en ninguna parte fuera del editor.
export default function Home({ usuario, setPaginaActual, nuevoWorkflow, abrirEnVisor, verWorkflow }) {
  const { t, idioma } = useIdioma();
  const [ejecuciones, setEjecuciones] = useState(null);   // null = cargando
  const [errorDescarga, setErrorDescarga] = useState(null);

  const descargar = (f) => {
    setErrorDescarga(null);
    descargarConToken(`/uploads/${f}`, f)
      .catch(err => setErrorDescarga(mensajeError(t('accion.descargar_fichero'), err, t)));
  };

  useEffect(() => {
    let vigente = true;
    apiFetch(`/ejecuciones/usuario/${usuario.id}?limit=${RECIENTES}`)
      .then(r => (r.ok ? r.json() : []))
      .catch(() => [])
      .then(datos => { if (vigente) setEjecuciones(datos); });
    return () => { vigente = false; };
  }, [usuario.id]);

  return (
    <div className="seccion-wrapper">
      <h2>{t('inicio.hola', { nombre: usuario.nombre })}</h2>

      <div className="inicio-acciones">
        <button className="btn-primary" onClick={nuevoWorkflow}>{t('cabecera.nuevo_workflow')}</button>
        <button className="btn-secundario" onClick={() => setPaginaActual('moleculas')}>
          {t('inicio.subir_moleculas')}
        </button>
        <button className="btn-secundario" onClick={() => setPaginaActual('algoritmos')}>
          {t('inicio.subir_algoritmo')}
        </button>
        <span className="inicio-tutorial">
          {t('inicio.primera_vez')}{' '}
          <button className="btn-enlace" onClick={() => setPaginaActual('tutorial')}>{t('inicio.ver_tutorial')}</button>
        </span>
      </div>

      <div className="subtitulo-tabla">
        <h3>{t('inicio.ultimas')}</h3>
        {ejecuciones?.length > 0 && (
          <button className="btn-enlace" onClick={() => setPaginaActual('peticiones')}>
            {t('inicio.ver_todos')}
          </button>
        )}
      </div>

      {ejecuciones === null && <p className="texto-secundario">{t('comun.cargando')}</p>}
      {errorDescarga && <p className="error-msg" role="status">{errorDescarga}</p>}

      {ejecuciones?.length === 0 && (
        <div className="panel inicio-vacio">
          <p>{t('inicio.vacio')}</p>
          <button className="btn-primary" onClick={() => setPaginaActual('moleculas')}>
            {t('inicio.subir_moleculas')}
          </button>
        </div>
      )}

      {ejecuciones?.length > 0 && (
        <div className="tabla-contenedor">
          <table className="tabla-peticiones">
            <thead>
              <tr>
                <th>{t('tabla.id')}</th>
                <th>{t('tabla.fecha')}</th>
                <th>{t('tabla.workflow')}</th>
                <th>{t('tabla.estado')}</th>
                <th>{t('tabla.ficheros')}</th>
                <th>{t('tabla.acciones')}</th>
              </tr>
            </thead>
            <tbody>
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
                  <td data-label={t('tabla.ficheros')}>
                    {e.archivos?.length
                      ? e.archivos.map(f => (
                          <span key={f} className="fichero-acciones">
                            <button
                              className="btn-descarga"
                              title={f}
                              onClick={() => descargar(f)}
                            >
                              {etiquetaFichero(f, t)}
                            </button>
                            <VerEn3D fichero={f} abrirEnVisor={abrirEnVisor} />
                          </span>
                        ))
                      : <span className="col-cifra">—</span>}
                  </td>
                  <td data-label={t('tabla.acciones')}>
                    <button className="btn-descarga" onClick={() => verWorkflow(e)}>
                      <Icono nombre="nodos" />{t('resultados.ver_workflow')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
