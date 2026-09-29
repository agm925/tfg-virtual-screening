import { useState, useEffect, useRef } from 'react'
import '../styles/Moleculas.css'
import MolViewer3D from './MolViewer3D'
import { apiFetch, descargarConToken } from '../api/client'

const EXT_MOLECULA = '.mol2,.sdf,.mol,.pdb,.pdbqt,.smi,.xyz'
const EXT_BD       = '.sdf'

export default function Moleculas() {
  const [archivos,     setArchivos]     = useState([])
  const [cargando,     setCargando]     = useState(false)
  const [msgMol,       setMsgMol]       = useState(null)
  const [msgBD,        setMsgBD]        = useState(null)
  const [fileMol,      setFileMol]      = useState(null)
  const [fileBD,       setFileBD]       = useState(null)
  const [filtroBuscar, setFiltroBuscar] = useState('')
  const [visor3D,      setVisor3D]      = useState(null) // nombre del archivo a visualizar
  const refMol = useRef()
  const refBD  = useRef()

  useEffect(() => { cargarArchivos() }, [])

  const cargarArchivos = async () => {
    try {
      const resp = await apiFetch('/moleculas')
      if (resp.ok) setArchivos(await resp.json())
    } catch { /* silent */ }
  }

  // ── Subida genérica ──────────────────────────────────────────────────────
  const subir = async (archivo, tipo, setMsg, resetRef) => {
    if (!archivo) { setMsg({ ok: false, texto: 'Selecciona un archivo primero.' }); return }
    setCargando(true); setMsg(null)
    const fd = new FormData()
    fd.append('archivo', archivo)
    fd.append('tipo',    tipo)
    try {
      const resp = await apiFetch('/moleculas/subir', { method: 'POST', body: fd })
      const data = await resp.json()
      if (resp.ok) {
        const extra = data.num_moleculas != null ? ` (${data.num_moleculas} moléculas)` : ''
        // El backend verifica el tipo contra el contenido real, no se fía de
        // lo que se marcó en el formulario (ver /moleculas/subir): un .sdf
        // con un único registro se guarda como molécula aunque se subiera
        // por "Base de Datos", y viceversa. Si ha corregido lo que se pidió,
        // se avisa -- si no, pasaría desapercibido y el fichero aparecería
        // en la columna "equivocada" sin explicación.
        const corregido = data.tipo && data.tipo !== tipo
          ? ` (guardado como ${data.tipo === 'base_de_datos' ? 'base de datos' : 'molécula individual'}` +
            `${data.tipo === 'molecula' ? ': solo tiene una molécula' : ': tiene varias moléculas'})`
          : ''
        setMsg({ ok: true, texto: `✅ "${data.nombre}" subido correctamente${extra}.${corregido}` })
        if (resetRef?.current) resetRef.current.value = ''
        tipo === 'molecula' ? setFileMol(null) : setFileBD(null)
        cargarArchivos()
      } else {
        setMsg({ ok: false, texto: `❌ ${data.detail || 'Error al subir'}` })
      }
    } catch (e) {
      setMsg({ ok: false, texto: `❌ Error de conexión: ${e.message}` })
    } finally {
      setCargando(false)
    }
  }

  // ── Borrar ───────────────────────────────────────────────────────────────
  // /uploads/{nombre} exige token (security-review): un <a href> normal no
  // puede llevar cabeceras, así que se descarga como blob autenticado.
  const descargar = async (nombre) => {
    try {
      await descargarConToken(`/uploads/${nombre}`, nombre)
    } catch (e) {
      alert(e.message)
    }
  }

  const borrar = async (nombre) => {
    if (!confirm(`¿Eliminar "${nombre}" del servidor?`)) return
    const resp = await apiFetch(`/moleculas/${encodeURIComponent(nombre)}`, { method: 'DELETE' })
    if (resp.ok) cargarArchivos()
    else {
      const data = await resp.json().catch(() => ({}))
      alert(data.detail || 'No se pudo eliminar el archivo')
    }
  }

  // ── Filtrado y clasificación ─────────────────────────────────────────────
  // `tipo` lo verifica el backend contra el contenido real al subir el
  // fichero (ver /moleculas/subir), no se adivina aquí por extensión y
  // tamaño: ese heurístico clasificaba mal cualquier .sdf pequeño con varias
  // moléculas diminutas, o cualquier .sdf grande con una sola.
  const lista = archivos.filter(a =>
    a.nombre.toLowerCase().includes(filtroBuscar.toLowerCase())
  )
  const moleculas = lista.filter(a => a.tipo !== 'base_de_datos')
  const bases     = lista.filter(a => a.tipo === 'base_de_datos')

  const puedeVer3D = (nombre) => /\.(sdf|mol2|mol|pdb)$/i.test(nombre)

  return (
    <div className="moleculas-page">
      {visor3D && <MolViewer3D archivo={visor3D} onClose={() => setVisor3D(null)} />}
      <div className="moleculas-hero">
        <h1>🧪 Biblioteca Molecular</h1>
        <p>Sube moléculas individuales o bases de datos completas para usarlas en el Constructor Visual.</p>
      </div>

      {/* ── Formularios ── */}
      <div className="formularios-grid">

        {/* Molécula individual */}
        <div className="card-upload">
          <div className="card-upload-header" style={{ background: 'linear-gradient(135deg,#3498db,#2980b9)' }}>
            <span className="card-upload-icon">🔬</span>
            <div>
              <h2>Molécula Individual</h2>
              <p>Un único compuesto en cualquier formato estándar</p>
            </div>
          </div>
          <div className="card-upload-body">
            <label className="upload-label">Formatos admitidos</label>
            <div className="formato-chips">
              {['mol2','sdf','mol','pdb','pdbqt','smi','xyz'].map(f => (
                <span key={f} className="chip">.{f}</span>
              ))}
            </div>
            <div
              className="drop-zone"
              onClick={() => refMol.current?.click()}
              onDragOver={e => e.preventDefault()}
              onDrop={e => { e.preventDefault(); setFileMol(e.dataTransfer.files[0]) }}
            >
              {fileMol
                ? <><span className="drop-icon">📄</span><span>{fileMol.name}</span></>
                : <><span className="drop-icon">⬆️</span><span>Arrastra aquí o haz clic para seleccionar</span></>
              }
            </div>
            <input
              ref={refMol}
              type="file"
              accept={EXT_MOLECULA}
              style={{ display: 'none' }}
              onChange={e => setFileMol(e.target.files[0])}
            />
            {msgMol && <p className={`upload-msg ${msgMol.ok ? 'ok' : 'err'}`}>{msgMol.texto}</p>}
            <button
              className="btn-subir azul"
              disabled={cargando || !fileMol}
              onClick={() => subir(fileMol, 'molecula', setMsgMol, refMol)}
            >
              {cargando ? 'Subiendo…' : '📤 Subir molécula'}
            </button>
          </div>
        </div>

        {/* Base de datos */}
        <div className="card-upload">
          <div className="card-upload-header" style={{ background: 'linear-gradient(135deg,#27ae60,#229954)' }}>
            <span className="card-upload-icon">🗄️</span>
            <div>
              <h2>Base de Datos</h2>
              <p>Archivo SDF con múltiples compuestos</p>
            </div>
          </div>
          <div className="card-upload-body">
            <label className="upload-label">Formato requerido</label>
            <div className="formato-chips">
              <span className="chip destacado">.sdf</span>
            </div>
            <div
              className="drop-zone"
              onClick={() => refBD.current?.click()}
              onDragOver={e => e.preventDefault()}
              onDrop={e => { e.preventDefault(); setFileBD(e.dataTransfer.files[0]) }}
            >
              {fileBD
                ? <><span className="drop-icon">🗂️</span><span>{fileBD.name}</span></>
                : <><span className="drop-icon">⬆️</span><span>Arrastra aquí o haz clic para seleccionar</span></>
              }
            </div>
            <input
              ref={refBD}
              type="file"
              accept={EXT_BD}
              style={{ display: 'none' }}
              onChange={e => setFileBD(e.target.files[0])}
            />
            <p className="hint-bd">
              💡 El archivo SDF puede contener cientos de moléculas. El sistema detectará automáticamente cuántas hay al subirlo.
            </p>
            {msgBD && <p className={`upload-msg ${msgBD.ok ? 'ok' : 'err'}`}>{msgBD.texto}</p>}
            <button
              className="btn-subir verde"
              disabled={cargando || !fileBD}
              onClick={() => subir(fileBD, 'base_de_datos', setMsgBD, refBD)}
            >
              {cargando ? 'Subiendo…' : '📤 Subir base de datos'}
            </button>
          </div>
        </div>
      </div>

      {/* ── Biblioteca actual ── */}
      <div className="biblioteca-section">
        <div className="biblioteca-header">
          <h2>📚 Archivos en el servidor</h2>
          <input
            className="buscador"
            placeholder="🔍 Buscar por nombre…"
            value={filtroBuscar}
            onChange={e => setFiltroBuscar(e.target.value)}
          />
          <button className="btn-refrescar" onClick={cargarArchivos}>🔄 Refrescar</button>
        </div>

        <div className="biblioteca-grid">
          {/* Moléculas individuales */}
          <div className="biblioteca-col">
            <h3>🔬 Moléculas individuales <span className="count">{moleculas.length}</span></h3>
            {moleculas.length === 0
              ? <p className="empty">No hay moléculas subidas todavía.</p>
              : moleculas.map(a => (
                  <div key={a.nombre} className="archivo-card">
                    <div className="archivo-info">
                      <span className="archivo-nombre">{a.nombre}</span>
                      <span className="archivo-meta">
                        {a.tamano_kb} KB · {a.nombre.split('.').pop().toUpperCase()}
                        {a.tipo === 'resultado' && ' · resultado propio'}
                      </span>
                    </div>
                    <div className="archivo-acciones">
                      {puedeVer3D(a.nombre) && (
                        <button className="btn-ver3d" onClick={() => setVisor3D(a.nombre)}>🔬 3D</button>
                      )}
                      <button onClick={() => descargar(a.nombre)} className="btn-dl">⬇️</button>
                      <button className="btn-del" onClick={() => borrar(a.nombre)}>🗑️</button>
                    </div>
                  </div>
                ))
            }
          </div>

          {/* Bases de datos */}
          <div className="biblioteca-col">
            <h3>🗄️ Bases de datos <span className="count">{bases.length}</span></h3>
            {bases.length === 0
              ? <p className="empty">No hay bases de datos subidas todavía.</p>
              : bases.map(a => (
                  <div key={a.nombre} className="archivo-card bd">
                    <div className="archivo-info">
                      <span className="archivo-nombre">{a.nombre}</span>
                      <span className="archivo-meta">
                        {a.tamano_kb} KB · SDF
                        {a.num_moleculas != null && ` · ${a.num_moleculas} moléculas`}
                      </span>
                    </div>
                    <div className="archivo-acciones">
                      <button onClick={() => descargar(a.nombre)} className="btn-dl">⬇️</button>
                      <button className="btn-del" onClick={() => borrar(a.nombre)}>🗑️</button>
                    </div>
                  </div>
                ))
            }
          </div>
        </div>
      </div>
    </div>
  )
}
