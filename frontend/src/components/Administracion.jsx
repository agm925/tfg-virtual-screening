import { useState, useEffect } from 'react'
import { apiFetch } from '../api/client'

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
  { id: 'usuarios',   label: '👤 Usuarios' },
  { id: 'algoritmos', label: '🧪 Algoritmos' },
  { id: 'moleculas',  label: '🧬 Moléculas' },
]

// `tipo` lo verifica el backend contra el contenido real al subir el
// fichero (GET /admin/moleculas), no se deduce de la visibilidad.
const ETIQUETA_TIPO = {
  molecula: '📁 molécula',
  base_de_datos: '🗄️ base de datos',
  resultado: '📊 resultado',
}

const estilos = {
  tabla:   { width: '100%', borderCollapse: 'collapse', fontSize: '14px', background: 'white' },
  th:      { textAlign: 'left', padding: '10px 12px', borderBottom: '2px solid #e5e8ec', color: '#2c3e50', whiteSpace: 'nowrap' },
  // textAlign explícito: #root fija `text-align: center` de forma global
  // (index.css), y a diferencia de `th` --que sí lo pone-- esta celda lo
  // heredaba sin querer. Resultado: la cabecera "Usuario" quedaba a la
  // izquierda y el contenido de la fila, centrado y desplazado a la derecha.
  td:      { padding: '10px 12px', borderBottom: '1px solid #eef1f4', verticalAlign: 'middle', textAlign: 'left' },
  // El color es explícito a propósito. Sin él, un botón hereda el color de
  // sistema `buttontext`, y como index.css declara `color-scheme: light dark`,
  // ese color pasa a ser BLANCO cuando el sistema operativo está en modo
  // oscuro: letras blancas sobre el fondo blanco del propio botón, es decir,
  // botones que parecen vacíos. El resto de la página no se entera porque
  // App.css fija `body { color: #333 }`, que los botones no heredan.
  boton:   { padding: '5px 10px', borderRadius: '6px', border: '1px solid #cfd6dd', background: 'white', color: '#2c3e50', cursor: 'pointer', fontSize: '13px' },
  peligro: { padding: '5px 10px', borderRadius: '6px', border: '1px solid #e6b0aa', background: '#fdf2f1', color: '#a93226', cursor: 'pointer', fontSize: '13px' },
  tenue:   { color: '#7f8c8d', fontSize: '13px' },
}

const Insignia = ({ ok, si, no }) => (
  <span style={{
    padding: '2px 8px', borderRadius: '10px', fontSize: '12px', whiteSpace: 'nowrap',
    background: ok ? '#e8f6ef' : '#fdf2f1',
    color:      ok ? '#1e8449' : '#a93226',
  }}>{ok ? si : no}</span>
)

export default function Administracion({ usuario }) {
  const [pestana, setPestana]   = useState('usuarios')
  const [usuarios, setUsuarios] = useState([])
  const [algoritmos, setAlgoritmos] = useState([])
  const [moleculas, setMoleculas]   = useState([])
  const [cargando, setCargando] = useState(true)
  const [error, setError]       = useState(null)
  const [aviso, setAviso]       = useState(null)

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
      if (!resp.ok) {
        setError(resp.status === 403
          ? 'Tu rol no tiene permiso para ver esta página.'
          : 'No se pudieron cargar los datos.')
        return
      }
      const datos = await resp.json()
      if (cual === 'usuarios')   setUsuarios(datos)
      if (cual === 'algoritmos') setAlgoritmos(datos)
      if (cual === 'moleculas')  setMoleculas(datos)
    } catch {
      setError('Error de conexión con la API.')
    } finally {
      setCargando(false)
    }
  }

  useEffect(() => { cargar(pestana) }, [pestana])

  // El backend responde 409 con un motivo legible cuando la operación dejaría
  // la plataforma sin administradores o cuando el admin intenta desactivarse
  // a sí mismo. Se muestra tal cual: explica mejor que un mensaje genérico.
  const aplicar = async (ruta, cuerpo, descripcion) => {
    setAviso(null)
    try {
      const resp = await apiFetch(ruta, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cuerpo),
      })
      if (!resp.ok) {
        const detalle = await resp.json().catch(() => null)
        setAviso({ tipo: 'error', texto: detalle?.detail || `No se pudo ${descripcion}.` })
        return
      }
      setAviso({ tipo: 'ok', texto: `Hecho: ${descripcion}.` })
      cargar()
    } catch {
      setAviso({ tipo: 'error', texto: 'Error de conexión con la API.' })
    }
  }

  const borrarMolecula = async (nombre) => {
    // Este sí es un borrado real e irreversible, así que se confirma.
    if (!window.confirm(`¿Eliminar definitivamente "${nombre}"?\n\nEl fichero se borra del disco y no se puede recuperar.`)) return
    setAviso(null)
    try {
      const resp = await apiFetch(`/moleculas/${encodeURIComponent(nombre)}`, { method: 'DELETE' })
      if (!resp.ok) {
        const detalle = await resp.json().catch(() => null)
        setAviso({ tipo: 'error', texto: detalle?.detail || 'No se pudo eliminar el fichero.' })
        return
      }
      setAviso({ tipo: 'ok', texto: `Fichero "${nombre}" eliminado.` })
      cargar('moleculas')
    } catch {
      setAviso({ tipo: 'error', texto: 'Error de conexión con la API.' })
    }
  }

  return (
    <div className="seccion-wrapper">
      <h2>🛡️ Administración</h2>
      <p className="seccion-subtitulo">
        Desactivar no borra: conserva el historial y se puede deshacer. Solo el
        borrado de ficheros es definitivo.
      </p>

      <div style={{ display: 'flex', gap: '8px', margin: '18px 0' }}>
        {PESTANAS.map(p => (
          <button
            key={p.id}
            onClick={() => setPestana(p.id)}
            style={{
              ...estilos.boton,
              fontWeight: pestana === p.id ? 600 : 400,
              background: pestana === p.id ? '#eaf2fb' : 'white',
              borderColor: pestana === p.id ? '#aac8e8' : '#cfd6dd',
            }}
          >{p.label}</button>
        ))}
      </div>

      {aviso && (
        <p style={{
          padding: '10px 14px', borderRadius: '8px', marginBottom: '14px',
          background: aviso.tipo === 'ok' ? '#e8f6ef' : '#fdf2f1',
          color:      aviso.tipo === 'ok' ? '#1e8449' : '#a93226',
        }}>{aviso.tipo === 'ok' ? '✅' : '⚠️'} {aviso.texto}</p>
      )}

      {cargando && <p>⏳ Cargando…</p>}
      {error && <p className="error-msg">❌ {error}</p>}

      {!cargando && !error && pestana === 'usuarios' && (
        <div style={{ overflowX: 'auto' }}>
          <table style={estilos.tabla}>
            <thead>
              <tr>
                <th style={estilos.th}>Usuario</th>
                <th style={estilos.th}>Rol</th>
                {/* El correo ya sale bajo el nombre, en la celda "Usuario":
                    esta columna es la insignia de verificado/sin verificar,
                    no el correo en sí. Con la cabecera "Correo" encima de esa
                    insignia parecía una columna descolocada. */}
                <th style={estilos.th}>Verificación</th>
                <th style={estilos.th}>Estado</th>
                <th style={estilos.th}>Trabajo</th>
                <th style={estilos.th}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {usuarios.map(u => {
                const esYo = u.id === usuario.id
                return (
                  <tr key={u.id}>
                    <td style={estilos.td}>
                      <strong>{u.nombre}</strong>{esYo && <span style={estilos.tenue}> (tú)</span>}
                      <div style={estilos.tenue}>{u.email}</div>
                    </td>
                    <td style={estilos.td}>
                      <Insignia ok={u.rol === 'admin'} si="admin" no="biólogo" />
                    </td>
                    <td style={estilos.td}>
                      <Insignia ok={u.email_verificado} si="verificado" no="sin verificar" />
                    </td>
                    <td style={estilos.td}>
                      <Insignia ok={u.activo} si="activo" no="desactivado" />
                    </td>
                    <td style={{ ...estilos.td, ...estilos.tenue }}>
                      {u.n_algoritmos} algoritmos · {u.n_peticiones} peticiones
                    </td>
                    <td style={estilos.td}>
                      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                        {!u.email_verificado && (
                          <button style={estilos.boton}
                            onClick={() => aplicar(`/admin/usuarios/${u.id}`, { email_verificado: true },
                              `verificar el correo de ${u.email}`)}>
                            Verificar correo
                          </button>
                        )}
                        {/* Sobre uno mismo no se ofrecen ni el cambio de rol ni
                            la desactivación: el backend los rechaza igualmente
                            con un 409, pero ofrecer un botón que siempre falla
                            es peor que no ofrecerlo. */}
                        {!esYo && (
                          <button style={estilos.boton}
                            onClick={() => aplicar(`/admin/usuarios/${u.id}`,
                              { rol: u.rol === 'admin' ? 'biologo' : 'admin' },
                              `cambiar el rol de ${u.email}`)}>
                            {u.rol === 'admin' ? 'Quitar admin' : 'Hacer admin'}
                          </button>
                        )}
                        {!esYo && (
                          <button style={u.activo ? estilos.peligro : estilos.boton}
                            onClick={() => aplicar(`/admin/usuarios/${u.id}`, { activo: !u.activo },
                              `${u.activo ? 'desactivar' : 'reactivar'} la cuenta de ${u.email}`)}>
                            {u.activo ? 'Desactivar' : 'Reactivar'}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {!cargando && !error && pestana === 'algoritmos' && (
        <div style={{ overflowX: 'auto' }}>
          <p style={estilos.tenue}>
            Desactivar un algoritmo lo retira del catálogo, rechaza las peticiones
            nuevas que lo pidan y detiene los workflows guardados que lo usen. Las
            peticiones ya ejecutadas conservan su historial.
          </p>
          <table style={{ ...estilos.tabla, marginTop: '12px' }}>
            <thead>
              <tr>
                <th style={estilos.th}>Algoritmo</th>
                <th style={estilos.th}>Tipo</th>
                <th style={estilos.th}>Fichero</th>
                <th style={estilos.th}>Visibilidad</th>
                <th style={estilos.th}>Estado</th>
                <th style={estilos.th}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {algoritmos.map(a => (
                <tr key={a.id} style={{ opacity: a.activo ? 1 : 0.6 }}>
                  <td style={estilos.td}>
                    <strong>{a.nombre}</strong>
                    <div style={estilos.tenue}>{a.descripcion}</div>
                  </td>
                  <td style={estilos.td}>{a.tipo}</td>
                  <td style={{ ...estilos.td, ...estilos.tenue }}>{a.ruta_archivo}</td>
                  <td style={estilos.td}>
                    <Insignia ok={a.es_publico} si="público" no="privado" />
                  </td>
                  <td style={estilos.td}>
                    <Insignia ok={a.activo} si="activo" no="retirado" />
                  </td>
                  <td style={estilos.td}>
                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                      <button style={estilos.boton}
                        onClick={() => aplicar(`/admin/algoritmos/${a.id}`, { es_publico: !a.es_publico },
                          `hacer ${a.es_publico ? 'privado' : 'público'} "${a.nombre}"`)}>
                        {a.es_publico ? 'Hacer privado' : 'Hacer público'}
                      </button>
                      <button style={a.activo ? estilos.peligro : estilos.boton}
                        onClick={() => aplicar(`/admin/algoritmos/${a.id}`, { activo: !a.activo },
                          `${a.activo ? 'retirar' : 'reactivar'} "${a.nombre}"`)}>
                        {a.activo ? 'Retirar del catálogo' : 'Reactivar'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!cargando && !error && pestana === 'moleculas' && (
        <div style={{ overflowX: 'auto' }}>
          <p style={estilos.tenue}>
            Todos los ficheros de <code>uploads/</code>, incluidos los resultados
            privados de cada usuario. Aquí el borrado sí es definitivo.
          </p>
          <table style={{ ...estilos.tabla, marginTop: '12px' }}>
            <thead>
              <tr>
                <th style={estilos.th}>Fichero</th>
                <th style={estilos.th}>Tipo</th>
                <th style={estilos.th}>Propietario</th>
                <th style={estilos.th}>Visibilidad</th>
                <th style={estilos.th}>Tamaño</th>
                <th style={estilos.th}>Fecha</th>
                <th style={estilos.th}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {moleculas.map(m => (
                <tr key={m.nombre}>
                  <td style={estilos.td}>{m.nombre}</td>
                  <td style={{ ...estilos.td, ...estilos.tenue }}>
                    {ETIQUETA_TIPO[m.tipo] || '—'}
                    {m.num_moleculas > 1 && ` (${m.num_moleculas})`}
                  </td>
                  <td style={{ ...estilos.td, ...estilos.tenue }}>
                    {m.propietario_email || 'sin propietario registrado'}
                  </td>
                  <td style={estilos.td}>
                    <Insignia ok={m.visibilidad === 'biblioteca'} si="biblioteca" no="resultado privado" />
                  </td>
                  <td style={estilos.td}>{m.tamano_kb} KB</td>
                  <td style={{ ...estilos.td, ...estilos.tenue }}>
                    {m.fecha_creacion ? new Date(m.fecha_creacion).toLocaleDateString('es-ES') : '—'}
                  </td>
                  <td style={estilos.td}>
                    <button style={estilos.peligro} onClick={() => borrarMolecula(m.nombre)}>
                      Eliminar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
