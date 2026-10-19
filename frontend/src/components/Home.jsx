import { useEffect, useState } from 'react'
import { apiFetch, descargarConToken } from '../api/client'
import { claseEstado, textoEstado, etiquetaFichero, formatFecha } from '../utils/ficheros'
import { mensajeError } from '../utils/mensajes'
import VerEn3D from './VerEn3D'
import Icono from './Icono'

// Cuántas ejecuciones recientes se enseñan aquí; el resto está en Resultados.
const RECIENTES = 5;

// Inicio es el banco de trabajo: lo que el usuario puede hacer ahora y lo
// último que ha lanzado, con sus ficheros a mano. Antes eran cuatro tarjetas
// de presentación iguales para todos, y los resultados de un cribado no
// aparecían en ninguna parte fuera del editor.
export default function Home({ usuario, setPaginaActual, nuevoWorkflow, abrirEnVisor, verWorkflow }) {
  const [ejecuciones, setEjecuciones] = useState(null);   // null = cargando
  const [errorDescarga, setErrorDescarga] = useState(null);

  const descargar = (f) => {
    setErrorDescarga(null);
    descargarConToken(`/uploads/${f}`, f)
      .catch(err => setErrorDescarga(mensajeError('descargar el fichero', err)));
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
      <h2>Hola, {usuario.nombre}</h2>

      <div className="inicio-acciones">
        <button className="btn-primary" onClick={nuevoWorkflow}>Nuevo workflow</button>
        <button className="btn-secundario" onClick={() => setPaginaActual('moleculas')}>
          Subir moléculas
        </button>
        <button className="btn-secundario" onClick={() => setPaginaActual('algoritmos')}>
          Subir algoritmo
        </button>
        <span className="inicio-tutorial">
          ¿Primera vez?{' '}
          <button className="btn-enlace" onClick={() => setPaginaActual('tutorial')}>Ver el tutorial</button>
        </span>
      </div>

      <div className="subtitulo-tabla">
        <h3>Tus últimas ejecuciones</h3>
        {ejecuciones?.length > 0 && (
          <button className="btn-enlace" onClick={() => setPaginaActual('peticiones')}>
            Ver todos los resultados
          </button>
        )}
      </div>

      {ejecuciones === null && <p className="texto-secundario">Cargando…</p>}
      {errorDescarga && <p className="error-msg" role="status">{errorDescarga}</p>}

      {ejecuciones?.length === 0 && (
        <div className="panel inicio-vacio">
          <p>
            Todavía no has lanzado ningún cribado. Empieza por subir una biblioteca de
            moléculas y después crea un workflow que la use.
          </p>
          <button className="btn-primary" onClick={() => setPaginaActual('moleculas')}>
            Subir moléculas
          </button>
        </div>
      )}

      {ejecuciones?.length > 0 && (
        <div className="tabla-contenedor">
          <table className="tabla-peticiones">
            <thead>
              <tr>
                <th>ID</th>
                <th>Fecha</th>
                <th>Workflow</th>
                <th>Estado</th>
                <th>Ficheros</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {ejecuciones.map(e => (
                <tr key={e.id}>
                  <td data-label="ID" className="col-id">#{e.id}</td>
                  <td data-label="Fecha" className="col-fecha">{formatFecha(e.fecha_ejecucion)}</td>
                  <td data-label="Workflow">
                    {e.workflow_nombre}
                    {e.workflow_borrado && <span className="texto-secundario"> (borrado)</span>}
                  </td>
                  <td data-label="Estado">
                    <span className={`badge ${claseEstado(e.estado)}`}>{textoEstado(e.estado)}</span>
                  </td>
                  <td data-label="Ficheros">
                    {e.archivos?.length
                      ? e.archivos.map(f => (
                          <span key={f} className="fichero-acciones">
                            <button
                              className="btn-descarga"
                              title={f}
                              onClick={() => descargar(f)}
                            >
                              {etiquetaFichero(f)}
                            </button>
                            <VerEn3D fichero={f} abrirEnVisor={abrirEnVisor} />
                          </span>
                        ))
                      : <span className="col-cifra">—</span>}
                  </td>
                  <td data-label="Acciones">
                    <button className="btn-descarga" onClick={() => verWorkflow(e)}>
                      <Icono nombre="nodos" />Ver workflow
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
