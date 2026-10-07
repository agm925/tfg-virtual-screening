import { useState, useEffect, useRef } from 'react'
import '../styles/Moleculas.css'
import VerEn3D from './VerEn3D'
import Icono from './Icono'
import { apiFetch, descargarConToken } from '../api/client'
import { errorDeRespuesta, mensajeError } from '../utils/mensajes'

const FORMATOS_MOLECULA = ['mol2', 'sdf', 'mol', 'pdb', 'pdbqt', 'smi', 'xyz']

// Zona para soltar o elegir un fichero. Es un boton (y no un div con onClick)
// para que tambien se pueda usar con el teclado.
function ZonaFichero({ fichero, accept, alElegir, id }) {
  const ref = useRef()
  return (
    <>
      <button
        type="button"
        className="zona-fichero"
        onClick={() => ref.current?.click()}
        onDragOver={e => e.preventDefault()}
        onDrop={e => { e.preventDefault(); alElegir(e.dataTransfer.files[0]) }}
        aria-describedby={`${id}-formatos`}
      >
        <Icono nombre={fichero ? 'fichero' : 'subir'} tamano={28} />
        <span>{fichero ? fichero.name : 'Arrastra el fichero aquí o haz clic para elegirlo'}</span>
      </button>
      <input
        ref={ref}
        id={id}
        type="file"
        accept={accept}
        hidden
        onChange={e => alElegir(e.target.files[0])}
      />
    </>
  )
}

// Un panel de subida: molecula suelta o biblioteca. `tipo` es lo que se pide
// al servidor; el servidor lo comprueba contra el contenido (ver mas abajo).
function PanelSubida({ tipo, titulo, explicacion, formatos, alSubir }) {
  const [fichero,  setFichero]  = useState(null)
  const [subiendo, setSubiendo] = useState(false)
  const [mensaje,  setMensaje]  = useState(null) // { tipo: 'exito'|'error', texto }
  const id = `subir-${tipo}`

  const subir = async () => {
    setSubiendo(true); setMensaje(null)
    const fd = new FormData()
    fd.append('archivo', fichero)
    fd.append('tipo', tipo)
    try {
      const resp = await apiFetch('/moleculas/subir', { method: 'POST', body: fd })
      if (!resp.ok) throw await errorDeRespuesta(resp)
      const data = await resp.json()
      const cuantas = data.num_moleculas > 1 ? ` con ${data.num_moleculas} moléculas` : ''
      // El backend verifica el tipo contra el contenido real, no se fía de
      // lo que se marcó en el formulario (ver /moleculas/subir): un .sdf con
      // un único registro se guarda como molécula aunque se subiera como
      // biblioteca, y viceversa. Si ha corregido lo que se pidió, se avisa:
      // si no, el fichero aparecería en la tabla "equivocada" sin explicación.
      const corregido = data.tipo && data.tipo !== tipo
        ? data.tipo === 'molecula'
          ? ' Solo tiene una molécula, así que se ha guardado como molécula individual.'
          : ' Tiene varias moléculas, así que se ha guardado como biblioteca.'
        : ''
      setMensaje({ tipo: 'exito', texto: `«${data.nombre}» subido${cuantas}.${corregido}` })
      setFichero(null)
      alSubir()
    } catch (err) {
      setMensaje({ tipo: 'error', texto: mensajeError('subir el fichero', err) })
    } finally {
      setSubiendo(false)
    }
  }

  return (
    <section className="panel panel-subida">
      <h3>{titulo}</h3>
      <p className="texto-secundario">{explicacion}</p>
      <ZonaFichero id={id} fichero={fichero} accept={formatos.map(f => `.${f}`).join(',')}
                   alElegir={f => { setFichero(f); setMensaje(null) }} />
      <p className="formatos" id={`${id}-formatos`}>
        Formatos: {formatos.map(f => <code key={f}>.{f}</code>)}
      </p>
      <button className="btn-primary" disabled={subiendo || !fichero} onClick={subir}>
        <Icono nombre="subir" />{subiendo ? 'Subiendo…' : 'Subir'}
      </button>
      {mensaje && (
        <p className={mensaje.tipo === 'exito' ? 'exito-msg' : 'error-msg'} role="status">{mensaje.texto}</p>
      )}
    </section>
  )
}

function TablaFicheros({ titulo, ficheros, vacio, conMoleculas, acciones }) {
  return (
    <>
      <h3 className="subtitulo-tabla">{titulo} <span className="contador">{ficheros.length}</span></h3>
      <div className="tabla-contenedor">
        <table className="tabla-peticiones tabla-ficheros">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Formato</th>
              {conMoleculas && <th>Moléculas</th>}
              <th>Tamaño</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {ficheros.length === 0 ? (
              <tr><td colSpan={conMoleculas ? 5 : 4} className="tabla-vacia">{vacio}</td></tr>
            ) : ficheros.map(a => (
              <tr key={a.nombre}>
                <td className="col-fichero" title={a.nombre}>
                  {a.nombre}
                  {a.tipo === 'resultado' && <span className="texto-secundario"> · resultado</span>}
                </td>
                <td>{a.nombre.split('.').pop().toUpperCase()}</td>
                {conMoleculas && <td className="col-cifra">{a.num_moleculas ?? '—'}</td>}
                <td className="col-cifra">{a.tamano_kb} KB</td>
                <td className="acciones-celda">{acciones(a)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

export default function Moleculas({ abrirEnVisor }) {
  const [archivos,     setArchivos]     = useState(null) // null = cargando
  const [errorLista,   setErrorLista]   = useState(null)
  const [aviso,        setAviso]        = useState(null) // errores de las acciones de las tablas
  const [filtroBuscar, setFiltroBuscar] = useState('')

  // Todos los cambios de estado van despues del await: al llamarse desde el
  // efecto de montaje no deben provocar un render en cascada.
  const cargarArchivos = async () => {
    try {
      const resp = await apiFetch('/moleculas')
      if (!resp.ok) throw await errorDeRespuesta(resp)
      setArchivos(await resp.json())
      setErrorLista(null)
    } catch (err) {
      // Antes el fallo se tragaba en silencio y la pagina decia "no hay
      // moleculas subidas" aunque las hubiera.
      setErrorLista(mensajeError('cargar la lista de ficheros', err))
      setArchivos(a => a ?? [])
    }
  }

  useEffect(() => { cargarArchivos() }, [])

  // /uploads/{nombre} exige token (security-review): un <a href> normal no
  // puede llevar cabeceras, así que se descarga como blob autenticado.
  const descargar = async (nombre) => {
    setAviso(null)
    try {
      await descargarConToken(`/uploads/${nombre}`, nombre)
    } catch (err) {
      setAviso(mensajeError('descargar el fichero', err))
    }
  }

  const borrar = async (nombre) => {
    if (!confirm(`¿Eliminar «${nombre}»? No se puede deshacer.`)) return
    setAviso(null)
    try {
      const resp = await apiFetch(`/moleculas/${encodeURIComponent(nombre)}`, { method: 'DELETE' })
      if (!resp.ok) throw await errorDeRespuesta(resp)
      cargarArchivos()
    } catch (err) {
      setAviso(mensajeError(`eliminar «${nombre}»`, err))
    }
  }

  // `tipo` lo verifica el backend contra el contenido real al subir el
  // fichero (ver /moleculas/subir), no se adivina aquí por extensión y
  // tamaño: ese heurístico clasificaba mal cualquier .sdf pequeño con varias
  // moléculas diminutas, o cualquier .sdf grande con una sola.
  const lista = (archivos || []).filter(a =>
    a.nombre.toLowerCase().includes(filtroBuscar.toLowerCase())
  )
  const moleculas = lista.filter(a => a.tipo !== 'base_de_datos')
  const bases     = lista.filter(a => a.tipo === 'base_de_datos')

  // También las bibliotecas: el visor las abre con su lista de moléculas y
  // su buscador, sin traerlas enteras (spec 002, RF-6 y RF-15). Los
  // resultados que salen aquí no: pueden ser de una ejecución en curso, que
  // el visor no ofrece (RF-2), y el botón acababa en un falso «ya no está
  // disponible». Los terminados tienen su «Ver en 3D» en Resultados.
  const acciones = (a) => (
    <>
      {a.tipo !== 'resultado' && <VerEn3D fichero={a.nombre} abrirEnVisor={abrirEnVisor} />}
      <button className="btn-descarga" onClick={() => descargar(a.nombre)}>
        <Icono nombre="bajar" />Descargar
      </button>
      <button className="btn-borrar" onClick={() => borrar(a.nombre)} aria-label={`Eliminar ${a.nombre}`}>
        <Icono nombre="papelera" />Eliminar
      </button>
    </>
  )

  return (
    <div className="seccion-wrapper">
      <h2>Moléculas</h2>
      <p className="seccion-subtitulo">
        Sube moléculas sueltas o bibliotecas SDF enteras para usarlas en tus workflows.
      </p>

      <div className="moleculas-subida">
        <PanelSubida
          tipo="molecula"
          titulo="Molécula individual"
          explicacion="Un único compuesto, en cualquiera de los formatos habituales."
          formatos={FORMATOS_MOLECULA}
          alSubir={cargarArchivos}
        />
        <PanelSubida
          tipo="base_de_datos"
          titulo="Biblioteca"
          explicacion="Un fichero SDF con muchos compuestos, para cribarlos todos de una vez. Al subirlo se cuentan las moléculas que tiene."
          formatos={['sdf']}
          alSubir={cargarArchivos}
        />
      </div>

      <div className="moleculas-buscar">
        <label htmlFor="moleculas-buscar">Buscar por nombre</label>
        <input id="moleculas-buscar" type="search" value={filtroBuscar}
               onChange={e => setFiltroBuscar(e.target.value)} />
        <button className="btn-secundario" onClick={cargarArchivos}>
          <Icono nombre="procesando" />Actualizar
        </button>
      </div>

      {errorLista && <p className="error-msg" role="status">{errorLista}</p>}
      {aviso && <p className="error-msg" role="status">{aviso}</p>}

      {archivos === null ? (
        <p className="texto-secundario">Cargando…</p>
      ) : (
        <>
          <TablaFicheros titulo="Moléculas individuales" ficheros={moleculas}
                         vacio={filtroBuscar ? 'Ninguna coincide con la búsqueda.' : 'Todavía no has subido ninguna molécula.'}
                         acciones={acciones} />
          <TablaFicheros titulo="Bibliotecas" ficheros={bases} conMoleculas
                         vacio={filtroBuscar ? 'Ninguna coincide con la búsqueda.' : 'Todavía no has subido ninguna biblioteca.'}
                         acciones={acciones} />
        </>
      )}
    </div>
  )
}
