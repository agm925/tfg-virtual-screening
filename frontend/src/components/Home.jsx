import { useEffect, useState } from 'react'
import { apiFetch, descargarConToken } from '../api/client'
import { claseEstado, textoEstado, etiquetaFichero, formatFecha } from '../utils/ficheros'

// Cuántas ejecuciones recientes se enseñan aquí; el resto está en Resultados.
const RECIENTES = 5;

// Inicio es el banco de trabajo: lo que el usuario puede hacer ahora y lo
// último que ha lanzado, con sus ficheros a mano. Antes eran cuatro tarjetas
// de presentación iguales para todos, y los resultados de un cribado no
// aparecían en ninguna parte fuera del editor.
export default function Home({ usuario, setPaginaActual, nuevoWorkflow }) {
  const [ejecuciones, setEjecuciones] = useState(null);   // null = cargando

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
              </tr>
            </thead>
            <tbody>
              {ejecuciones.map(e => (
                <tr key={e.id}>
                  <td className="col-id">#{e.id}</td>
                  <td className="col-fecha">{formatFecha(e.fecha_ejecucion)}</td>
                  <td>{e.workflow_nombre}</td>
                  <td>
                    <span className={`badge ${claseEstado(e.estado)}`}>{textoEstado(e.estado)}</span>
                  </td>
                  <td>
                    {e.archivos?.length
                      ? e.archivos.map(f => (
                          <button
                            key={f}
                            className="btn-descarga"
                            title={f}
                            onClick={() => descargarConToken(`/uploads/${f}`, f).catch(err => alert(err.message))}
                          >
                            {etiquetaFichero(f)}
                          </button>
                        ))
                      : <span className="col-cifra">—</span>}
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
