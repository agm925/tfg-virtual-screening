import { useState, useEffect } from 'react'
import { apiFetch } from '../api/client'
import Icono from './Icono'
import { tipoNodo, ETIQUETA_ALGORITMO } from '../utils/tiposNodo'
import { formatFecha } from '../utils/ficheros'
import { errorDeRespuesta, mensajeError } from '../utils/mensajes'
import { useIdioma } from '../hooks/useIdioma'

// Panel de administración de la plataforma.
//
// La acción central no es borrar, es DESACTIVAR (ver el bloque de endpoints
// /admin en app/main.py). Un usuario tiene peticiones, workflows y ficheros
// colgando por clave foránea, y sus moléculas pueden estar en la biblioteca
// compartida referenciadas desde los grafos guardados de OTROS usuarios;
// un algoritmo tiene peticiones que apuntan a él. Por eso aquí se conmuta
// "Activo" en vez de ofrecer una papelera: conserva el historial y se puede
// deshacer. El único borrado real es el de ficheros sueltos.

const PESTANAS = [
  { id: 'usuarios',   texto: 'admin.usuarios' },
  { id: 'algoritmos', texto: 'cabecera.algoritmos' },
  { id: 'moleculas',  texto: 'tabla.ficheros' },
]

// `tipo` lo verifica el backend contra el contenido real al subir el
// fichero (GET /admin/moleculas), no se deduce de la visibilidad.
const ETIQUETA_TIPO = {
  molecula: 'tabla.molecula',
  base_de_datos: 'moleculas.biblioteca',
  resultado: 'admin.resultado',
}

// Insignia de dos estados con las clases de App.css (.badge.*): `si` cuando
// la condición se cumple, `no` cuando no.
const Insignia = ({ ok, si, no, claseSi = 'completado', claseNo = 'cancelado' }) => (
  <span className={`badge ${ok ? claseSi : claseNo}`}>{ok ? si : no}</span>
)

// La ruta del script es cosa del servidor: al administrador le basta con el
// nombre del fichero para reconocerlo.
const nombreFichero = (ruta) => (ruta || '').replace(/\\/g, '/').split('/').pop()

export default function Administracion({ usuario }) {
  const { t, idioma } = useIdioma()
  const [pestana, setPestana]   = useState('usuarios')
  const [usuarios, setUsuarios] = useState([])
  const [algoritmos, setAlgoritmos] = useState([])
  const [moleculas, setMoleculas]   = useState([])
  const [cargando, setCargando] = useState(true)
  const [error, setError]       = useState(null)
  const [aviso, setAviso]       = useState(null) // { tipo: 'exito'|'error', texto }

  // Una sola función de carga para las tres pestañas: cambiar de pestaña
  // recarga sus datos, de modo que lo que se ve nunca es un listado obsoleto
  // de hace varios minutos.
  const cargar = async (cual = pestana) => {
    setCargando(true)
    setError(null)
    const rutas = {
      usuarios:   '/admin/usuarios?limit=500',
      // incluir_inactivos: el catálogo normal oculta los desactivados --ese es
      // justo su efecto-- pero el panel tiene que verlos para reactivarlos.
      algoritmos: '/algoritmos?limit=500&incluir_inactivos=true',
      moleculas:  '/admin/moleculas?limit=500',
    }
    try {
      const resp = await apiFetch(rutas[cual])
      if (resp.status === 403) {
        setError(t('admin.sin_permiso'))
        return
      }
      if (!resp.ok) throw await errorDeRespuesta(resp)
      const datos = await resp.json()
      if (cual === 'usuarios')   setUsuarios(datos)
      if (cual === 'algoritmos') setAlgoritmos(datos)
      if (cual === 'moleculas')  setMoleculas(datos)
    } catch (err) {
      setError(mensajeError(t('accion.cargar_informacion'), err, t))
    } finally {
      setCargando(false)
    }
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { cargar(pestana) }, [pestana])

  // El backend responde 409 con un motivo legible cuando la operación dejaría
  // la plataforma sin administradores o cuando el admin intenta desactivarse
  // a sí mismo: mensajeError lo enseña, porque explica mejor que uno genérico.
  const aplicar = async (ruta, cuerpo, accion, hecho) => {
    setAviso(null)
    try {
      const resp = await apiFetch(ruta, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cuerpo),
      })
      if (!resp.ok) throw await errorDeRespuesta(resp)
      setAviso({ tipo: 'exito', texto: hecho })
      cargar()
    } catch (err) {
      setAviso({ tipo: 'error', texto: mensajeError(accion, err, t) })
    }
  }

  const borrarMolecula = async (nombre) => {
    // Este sí es un borrado real e irreversible, así que se confirma.
    if (!window.confirm(t('admin.confirmar_eliminar', { nombre }))) return
    setAviso(null)
    try {
      const resp = await apiFetch(`/moleculas/${encodeURIComponent(nombre)}`, { method: 'DELETE' })
      if (!resp.ok) throw await errorDeRespuesta(resp)
      setAviso({ tipo: 'exito', texto: t('admin.eliminado', { nombre }) })
      cargar('moleculas')
    } catch (err) {
      setAviso({ tipo: 'error', texto: mensajeError(t('accion.eliminar', { nombre }), err, t) })
    }
  }

  return (
    <div className="seccion-wrapper">
      <h2>{t('cabecera.administracion')}</h2>
      <p className="seccion-subtitulo">{t('admin.subtitulo')}</p>

      <div className="pestanas" role="tablist" aria-label={t('admin.que_administrar')}>
        {PESTANAS.map(p => (
          <button
            key={p.id}
            role="tab"
            aria-selected={pestana === p.id}
            className={`pestana ${pestana === p.id ? 'activa' : ''}`}
            onClick={() => { setAviso(null); setPestana(p.id) }}
          >{t(p.texto)}</button>
        ))}
      </div>

      {aviso && (
        <p className={aviso.tipo === 'exito' ? 'exito-msg' : 'error-msg'} role="status">{aviso.texto}</p>
      )}

      {cargando && <p className="texto-secundario">{t('comun.cargando')}</p>}
      {error && <p className="error-msg" role="status">{error}</p>}

      {!cargando && !error && pestana === 'usuarios' && (
        <div className="tabla-contenedor">
          <table className="tabla-peticiones">
            <thead>
              <tr>
                <th>{t('admin.usuario')}</th>
                <th>{t('admin.rol')}</th>
                {/* El correo ya sale bajo el nombre, en la celda "Usuario":
                    esta columna es la insignia de verificado/sin verificar,
                    no el correo en sí. */}
                <th>{t('admin.verificacion')}</th>
                <th>{t('tabla.estado')}</th>
                <th>{t('admin.trabajo')}</th>
                <th>{t('tabla.acciones')}</th>
              </tr>
            </thead>
            <tbody>
              {usuarios.map(u => {
                const esYo = u.id === usuario.id
                return (
                  <tr key={u.id}>
                    <td data-label={t('admin.usuario')}>
                      <strong>{u.nombre}</strong>{esYo && <span className="texto-secundario"> {t('admin.tu')}</span>}
                      <div className="texto-secundario">{u.email}</div>
                    </td>
                    <td data-label={t('admin.rol')}><Insignia ok={u.rol === 'admin'} si={t('admin.administrador')} no={t('admin.biologo')} claseSi="procesando" /></td>
                    <td data-label={t('admin.verificacion')}><Insignia ok={u.email_verificado} si={t('admin.verificado')} no={t('admin.sin_verificar')} claseNo="pendiente" /></td>
                    <td data-label={t('tabla.estado')}><Insignia ok={u.activo} si={t('admin.activo')} no={t('admin.desactivado')} /></td>
                    <td data-label={t('admin.trabajo')} className="col-cifra">
                      {t('admin.trabajo_n', { algoritmos: u.n_algoritmos, peticiones: u.n_peticiones })}
                    </td>
                    <td data-label={t('tabla.acciones')} className="acciones-celda">
                      {!u.email_verificado && (
                        <button className="btn-descarga"
                          onClick={() => aplicar(`/admin/usuarios/${u.id}`, { email_verificado: true },
                            t('admin.accion_verificar', { email: u.email }), t('admin.hecho_verificar', { email: u.email }))}>
                          {t('admin.verificar_correo')}
                        </button>
                      )}
                      {/* Sobre uno mismo no se ofrecen ni el cambio de rol ni
                          la desactivación: el backend los rechaza igualmente
                          con un 409, pero ofrecer un botón que siempre falla
                          es peor que no ofrecerlo. */}
                      {!esYo && (
                        <button className="btn-descarga"
                          onClick={() => aplicar(`/admin/usuarios/${u.id}`,
                            { rol: u.rol === 'admin' ? 'biologo' : 'admin' },
                            t('admin.accion_rol', { email: u.email }),
                            t(u.rol === 'admin' ? 'admin.hecho_biologo' : 'admin.hecho_admin', { email: u.email }))}>
                          {t(u.rol === 'admin' ? 'admin.quitar_admin' : 'admin.hacer_admin')}
                        </button>
                      )}
                      {!esYo && (
                        <button className={u.activo ? 'btn-borrar' : 'btn-descarga'}
                          onClick={() => aplicar(`/admin/usuarios/${u.id}`, { activo: !u.activo },
                            t(u.activo ? 'admin.accion_desactivar' : 'admin.accion_reactivar_cuenta', { email: u.email }),
                            t(u.activo ? 'admin.hecho_desactivada' : 'admin.hecho_reactivada', { email: u.email }))}>
                          {t(u.activo ? 'admin.desactivar' : 'admin.reactivar')}
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {!cargando && !error && pestana === 'algoritmos' && (
        <>
          <p className="texto-secundario">
            {t('admin.retirar_texto')}
          </p>
          <div className="tabla-contenedor">
            <table className="tabla-peticiones">
              <thead>
                <tr>
                  <th>{t('tabla.algoritmo')}</th>
                  <th>{t('admin.tipo')}</th>
                  <th>{t('visor.fichero')}</th>
                  <th>{t('admin.visibilidad')}</th>
                  <th>{t('tabla.estado')}</th>
                  <th>{t('tabla.acciones')}</th>
                </tr>
              </thead>
              <tbody>
                {algoritmos.map(a => (
                  <tr key={a.id} className={a.activo ? '' : 'fila-inactiva'}>
                    <td data-label={t('tabla.algoritmo')}>
                      <strong>{a.nombre}</strong>
                      <div className="texto-secundario">{a.descripcion}</div>
                    </td>
                    <td data-label={t('admin.tipo')} className="celda-tipo">
                      {tipoNodo(a.tipo) && <Icono nombre={tipoNodo(a.tipo).icono} />}
                      {ETIQUETA_ALGORITMO[a.tipo] ? t(ETIQUETA_ALGORITMO[a.tipo]) : a.tipo}
                    </td>
                    <td data-label={t('visor.fichero')} className="col-fichero">{nombreFichero(a.ruta_archivo)}</td>
                    <td data-label={t('admin.visibilidad')}><Insignia ok={a.es_publico} si={t('visibilidad.publico')} no={t('visibilidad.privado')} claseSi="procesando" /></td>
                    <td data-label={t('tabla.estado')}><Insignia ok={a.activo} si={t('admin.activo')} no={t('admin.retirado')} claseNo="error" /></td>
                    <td data-label={t('tabla.acciones')} className="acciones-celda">
                      <button className="btn-descarga"
                        onClick={() => aplicar(`/admin/algoritmos/${a.id}`, { es_publico: !a.es_publico },
                          t(a.es_publico ? 'admin.accion_privado' : 'admin.accion_publico', { nombre: a.nombre }),
                          t(a.es_publico ? 'admin.hecho_privado' : 'admin.hecho_publico', { nombre: a.nombre }))}>
                        {t(a.es_publico ? 'admin.hacer_privado' : 'admin.hacer_publico')}
                      </button>
                      <button className={a.activo ? 'btn-borrar' : 'btn-descarga'}
                        onClick={() => aplicar(`/admin/algoritmos/${a.id}`, { activo: !a.activo },
                          t(a.activo ? 'admin.accion_retirar' : 'admin.accion_reactivar', { nombre: a.nombre }),
                          t(a.activo ? 'admin.hecho_retirado' : 'admin.hecho_reactivado', { nombre: a.nombre }))}>
                        {t(a.activo ? 'admin.retirar' : 'admin.reactivar')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!cargando && !error && pestana === 'moleculas' && (
        <>
          <p className="texto-secundario">
            {t('admin.ficheros_texto')}
          </p>
          <div className="tabla-contenedor">
            <table className="tabla-peticiones">
              <thead>
                <tr>
                  <th>{t('visor.fichero')}</th>
                  <th>{t('admin.tipo')}</th>
                  <th>{t('admin.propietario')}</th>
                  <th>{t('admin.visibilidad')}</th>
                  <th>{t('tabla.tamano')}</th>
                  <th>{t('tabla.fecha')}</th>
                  <th>{t('tabla.acciones')}</th>
                </tr>
              </thead>
              <tbody>
                {moleculas.map(m => (
                  <tr key={m.nombre}>
                    <td data-label={t('visor.fichero')} className="col-fichero">{m.nombre}</td>
                    <td data-label={t('admin.tipo')}>
                      {ETIQUETA_TIPO[m.tipo] ? t(ETIQUETA_TIPO[m.tipo]) : '—'}
                      {m.num_moleculas > 1 && <span className="texto-secundario"> ({t('visor.n_moleculas', { n: m.num_moleculas })})</span>}
                    </td>
                    <td data-label={t('admin.propietario')} className="texto-secundario">
                      {m.propietario_email || t('admin.sin_propietario')}
                    </td>
                    <td data-label={t('admin.visibilidad')}>
                      <Insignia ok={m.visibilidad === 'biblioteca'} si={t('moleculas.biblioteca')} no={t('admin.resultado_privado')} claseSi="procesando" />
                    </td>
                    <td data-label={t('tabla.tamano')} className="col-cifra">{m.tamano_kb} KB</td>
                    <td data-label={t('tabla.fecha')} className="col-fecha">{formatFecha(m.fecha_creacion, idioma)}</td>
                    <td data-label={t('tabla.acciones')} className="acciones-celda">
                      <button className="btn-borrar" onClick={() => borrarMolecula(m.nombre)}
                              aria-label={t('moleculas.eliminar_nombre', { nombre: m.nombre })}>
                        <Icono nombre="papelera" />{t('comun.eliminar')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
