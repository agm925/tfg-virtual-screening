import { useState, useEffect } from 'react'
import { apiFetch } from '../api/client'
import Icono from './Icono'
import { tipoNodo, ETIQUETA_ALGORITMO } from '../utils/tiposNodo'
import { formatFecha } from '../utils/ficheros'
import { errorDeRespuesta, mensajeError } from '../utils/mensajes'

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
  { id: 'usuarios',   label: 'Usuarios' },
  { id: 'algoritmos', label: 'Algoritmos' },
  { id: 'moleculas',  label: 'Ficheros' },
]

// `tipo` lo verifica el backend contra el contenido real al subir el
// fichero (GET /admin/moleculas), no se deduce de la visibilidad.
const ETIQUETA_TIPO = {
  molecula: 'Molécula',
  base_de_datos: 'Biblioteca',
  resultado: 'Resultado',
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
        setError('Tu cuenta no tiene permiso para ver esta página.')
        return
      }
      if (!resp.ok) throw await errorDeRespuesta(resp)
      const datos = await resp.json()
      if (cual === 'usuarios')   setUsuarios(datos)
      if (cual === 'algoritmos') setAlgoritmos(datos)
      if (cual === 'moleculas')  setMoleculas(datos)
    } catch (err) {
      setError(mensajeError('cargar la información', err))
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
      setAviso({ tipo: 'error', texto: mensajeError(accion, err) })
    }
  }

  const borrarMolecula = async (nombre) => {
    // Este sí es un borrado real e irreversible, así que se confirma.
    if (!window.confirm(`¿Eliminar definitivamente «${nombre}»?\n\nEl fichero se borra del disco y no se puede recuperar.`)) return
    setAviso(null)
    try {
      const resp = await apiFetch(`/moleculas/${encodeURIComponent(nombre)}`, { method: 'DELETE' })
      if (!resp.ok) throw await errorDeRespuesta(resp)
      setAviso({ tipo: 'exito', texto: `«${nombre}» eliminado.` })
      cargar('moleculas')
    } catch (err) {
      setAviso({ tipo: 'error', texto: mensajeError(`eliminar «${nombre}»`, err) })
    }
  }

  return (
    <div className="seccion-wrapper">
      <h2>Administración</h2>
      <p className="seccion-subtitulo">
        Desactivar no borra: conserva el historial y se puede deshacer. Solo el
        borrado de ficheros es definitivo.
      </p>

      <div className="pestanas" role="tablist" aria-label="Qué administrar">
        {PESTANAS.map(p => (
          <button
            key={p.id}
            role="tab"
            aria-selected={pestana === p.id}
            className={`pestana ${pestana === p.id ? 'activa' : ''}`}
            onClick={() => { setAviso(null); setPestana(p.id) }}
          >{p.label}</button>
        ))}
      </div>

      {aviso && (
        <p className={aviso.tipo === 'exito' ? 'exito-msg' : 'error-msg'} role="status">{aviso.texto}</p>
      )}

      {cargando && <p className="texto-secundario">Cargando…</p>}
      {error && <p className="error-msg" role="status">{error}</p>}

      {!cargando && !error && pestana === 'usuarios' && (
        <div className="tabla-contenedor">
          <table className="tabla-peticiones">
            <thead>
              <tr>
                <th>Usuario</th>
                <th>Rol</th>
                {/* El correo ya sale bajo el nombre, en la celda "Usuario":
                    esta columna es la insignia de verificado/sin verificar,
                    no el correo en sí. */}
                <th>Verificación</th>
                <th>Estado</th>
                <th>Trabajo</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {usuarios.map(u => {
                const esYo = u.id === usuario.id
                return (
                  <tr key={u.id}>
                    <td>
                      <strong>{u.nombre}</strong>{esYo && <span className="texto-secundario"> (tú)</span>}
                      <div className="texto-secundario">{u.email}</div>
                    </td>
                    <td><Insignia ok={u.rol === 'admin'} si="Administrador" no="Biólogo" claseSi="procesando" /></td>
                    <td><Insignia ok={u.email_verificado} si="Verificado" no="Sin verificar" claseNo="pendiente" /></td>
                    <td><Insignia ok={u.activo} si="Activo" no="Desactivado" /></td>
                    <td className="col-cifra">
                      {u.n_algoritmos} algoritmos · {u.n_peticiones} peticiones
                    </td>
                    <td className="acciones-celda">
                      {!u.email_verificado && (
                        <button className="btn-descarga"
                          onClick={() => aplicar(`/admin/usuarios/${u.id}`, { email_verificado: true },
                            `verificar el correo de ${u.email}`, `Correo de ${u.email} verificado.`)}>
                          Verificar correo
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
                            `cambiar el rol de ${u.email}`,
                            `${u.email} ahora es ${u.rol === 'admin' ? 'biólogo' : 'administrador'}.`)}>
                          {u.rol === 'admin' ? 'Quitar administrador' : 'Hacer administrador'}
                        </button>
                      )}
                      {!esYo && (
                        <button className={u.activo ? 'btn-borrar' : 'btn-descarga'}
                          onClick={() => aplicar(`/admin/usuarios/${u.id}`, { activo: !u.activo },
                            `${u.activo ? 'desactivar' : 'reactivar'} la cuenta de ${u.email}`,
                            `Cuenta de ${u.email} ${u.activo ? 'desactivada' : 'reactivada'}.`)}>
                          {u.activo ? 'Desactivar' : 'Reactivar'}
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
            Retirar un algoritmo lo quita del catálogo, rechaza las peticiones
            nuevas que lo pidan y detiene los workflows guardados que lo usen. Las
            peticiones ya ejecutadas conservan su historial.
          </p>
          <div className="tabla-contenedor">
            <table className="tabla-peticiones">
              <thead>
                <tr>
                  <th>Algoritmo</th>
                  <th>Tipo</th>
                  <th>Fichero</th>
                  <th>Visibilidad</th>
                  <th>Estado</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {algoritmos.map(a => (
                  <tr key={a.id} className={a.activo ? '' : 'fila-inactiva'}>
                    <td>
                      <strong>{a.nombre}</strong>
                      <div className="texto-secundario">{a.descripcion}</div>
                    </td>
                    <td className="celda-tipo">
                      {tipoNodo(a.tipo) && <Icono nombre={tipoNodo(a.tipo).icono} />}
                      {ETIQUETA_ALGORITMO[a.tipo] || a.tipo}
                    </td>
                    <td className="col-fichero">{nombreFichero(a.ruta_archivo)}</td>
                    <td><Insignia ok={a.es_publico} si="Público" no="Privado" claseSi="procesando" /></td>
                    <td><Insignia ok={a.activo} si="Activo" no="Retirado" claseNo="error" /></td>
                    <td className="acciones-celda">
                      <button className="btn-descarga"
                        onClick={() => aplicar(`/admin/algoritmos/${a.id}`, { es_publico: !a.es_publico },
                          `hacer ${a.es_publico ? 'privado' : 'público'} «${a.nombre}»`,
                          `«${a.nombre}» ahora es ${a.es_publico ? 'privado' : 'público'}.`)}>
                        {a.es_publico ? 'Hacer privado' : 'Hacer público'}
                      </button>
                      <button className={a.activo ? 'btn-borrar' : 'btn-descarga'}
                        onClick={() => aplicar(`/admin/algoritmos/${a.id}`, { activo: !a.activo },
                          `${a.activo ? 'retirar' : 'reactivar'} «${a.nombre}»`,
                          `«${a.nombre}» ${a.activo ? 'retirado del catálogo' : 'reactivado'}.`)}>
                        {a.activo ? 'Retirar del catálogo' : 'Reactivar'}
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
            Todos los ficheros subidos o generados en la plataforma, incluidos los
            resultados privados de cada usuario. Aquí el borrado sí es definitivo.
          </p>
          <div className="tabla-contenedor">
            <table className="tabla-peticiones">
              <thead>
                <tr>
                  <th>Fichero</th>
                  <th>Tipo</th>
                  <th>Propietario</th>
                  <th>Visibilidad</th>
                  <th>Tamaño</th>
                  <th>Fecha</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {moleculas.map(m => (
                  <tr key={m.nombre}>
                    <td className="col-fichero">{m.nombre}</td>
                    <td>
                      {ETIQUETA_TIPO[m.tipo] || '—'}
                      {m.num_moleculas > 1 && <span className="texto-secundario"> ({m.num_moleculas} moléculas)</span>}
                    </td>
                    <td className="texto-secundario">
                      {m.propietario_email || 'Sin propietario registrado'}
                    </td>
                    <td>
                      <Insignia ok={m.visibilidad === 'biblioteca'} si="Biblioteca" no="Resultado privado" claseSi="procesando" />
                    </td>
                    <td className="col-cifra">{m.tamano_kb} KB</td>
                    <td className="col-fecha">{formatFecha(m.fecha_creacion)}</td>
                    <td className="acciones-celda">
                      <button className="btn-borrar" onClick={() => borrarMolecula(m.nombre)}
                              aria-label={`Eliminar ${m.nombre}`}>
                        <Icono nombre="papelera" />Eliminar
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
