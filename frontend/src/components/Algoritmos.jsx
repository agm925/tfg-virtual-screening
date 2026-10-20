import { useState } from 'react'
import { apiFetch } from '../api/client'
import Icono from './Icono'
import { tipoNodo, ETIQUETA_ALGORITMO } from '../utils/tiposNodo'
import { mensajeError, textoDetalle } from '../utils/mensajes'
import {
  MAX_ENTRADAS, MAX_OPCIONES, interfazPorDefecto, vistaPreviaLlamada,
} from '../utils/interfaz'
import { useIdioma } from '../hooks/useIdioma'
import SelectorFichero from './SelectorFichero'
import '../styles/Algoritmos.css'

// Un único formulario con un selector de tipo, en lugar de los cuatro
// formularios separados que había antes.
//
// El cambio no es solo de presentación: el tipo que elige el autor es lo que
// le dice al banco de pruebas CÓMO invocar el algoritmo --una molécula, dos, o
// ligando más receptor-- antes de aceptarlo. Con cuatro formularios, elegir el
// equivocado se traducía en un mensaje de "el tipo no coincide"; ahora es un
// campo explícito y la plataforma verifica que la declaración sea cierta.
//
// El icono y el color de cada tipo son los del nodo que lo usa en el editor
// (utils/tiposNodo.js): quien sube un algoritmo de docking lo reconoce luego
// en el nodo Docking. `etiqueta` y `resumen` son claves de los diccionarios.
const TIPOS = [
  {
    valor: 'preprocesado',
    etiqueta: ETIQUETA_ALGORITMO.preprocesado,
    resumen: 'algoritmos.resumen_preprocesado',
  },
  {
    valor: 'alineacion',
    etiqueta: ETIQUETA_ALGORITMO.alineacion,
    resumen: 'algoritmos.resumen_alineacion',
  },
  {
    valor: 'comparacion',
    etiqueta: ETIQUETA_ALGORITMO.comparacion,
    resumen: 'algoritmos.resumen_comparacion',
  },
  {
    valor: 'docking',
    etiqueta: ETIQUETA_ALGORITMO.docking,
    resumen: 'algoritmos.resumen_docking',
  },
]

// Los nombres de las entradas por defecto van en el idioma de la interfaz.
const estadoInicial = (t) => ({
  nombre: '', descripcion: '', tipo: 'preprocesado', archivo: null,
  interfaz: interfazPorDefecto('preprocesado', t),
  cargando: false, resultado: null,
})

// Cómo se llama al script (spec 013): sus entradas, cómo recibe la salida y
// sus opciones. El banco lo prueba con esta llamada, y el nodo del Constructor
// tendrá un conector por entrada y una casilla por opción. Las filas de
// opción sin rellenar no se mandan.
function interfazParaEnviar(interfaz) {
  return {
    ...interfaz,
    opciones: interfaz.opciones.filter(o => o.opcion.trim() || o.nombre.trim()),
  }
}

export default function Algoritmos() {
  const { t } = useIdioma()
  const [form, setForm] = useState(() => estadoInicial(t))
  const tipoActual = TIPOS.find(tipo => tipo.valor === form.tipo)

  const registrarAlgoritmo = async (e) => {
    e.preventDefault()
    // El selector de ficheros va oculto (SelectorFichero) y el navegador no
    // puede exigirlo con `required`: se comprueba aquí.
    if (!form.archivo) {
      setForm(s => ({ ...s, resultado: { ok: false, mensaje: t('algoritmos.falta_script') } }))
      return
    }
    setForm(s => ({ ...s, cargando: true, resultado: null }))

    const formData = new FormData()
    formData.append('nombre', form.nombre)
    formData.append('descripcion', form.descripcion)
    formData.append('tipo', form.tipo)
    formData.append('es_publico', true)
    formData.append('archivo', form.archivo)
    formData.append('interfaz', JSON.stringify(interfazParaEnviar(form.interfaz)))

    try {
      const resp = await apiFetch('/algoritmos', { method: 'POST', body: formData })
      const datos = await resp.json().catch(() => ({}))

      if (resp.ok) {
        setForm({
          ...estadoInicial(t),
          tipo: form.tipo,
          interfaz: interfazPorDefecto(form.tipo, t),
          resultado: {
            ok: true,
            nombre: datos.nombre,
            formato: datos.formato_salida,
            clave: datos.clave_score,
            llamada: vistaPreviaLlamada(datos.ruta_archivo, datos.interfaz || interfazPorDefecto(datos.tipo, t), t),
          },
        })
        return
      }

      // 422 = no ha superado el banco de pruebas. El backend devuelve un
      // objeto con mensaje, motivo, detalle, salida y ayuda. Mensaje, motivo
      // y ayuda van a la vista, limpios de rutas; lo que devolvio el script y
      // su consola, plegados en "Detalles tecnicos": los necesita quien
      // escribio el .py para arreglarlo, pero no se imponen a nadie.
      const d = datos.detail
      if (resp.status === 422 && d && typeof d === 'object' && !Array.isArray(d)) {
        setForm(s => ({ ...s, resultado: {
          ok: false,
          mensaje: textoDetalle(d.mensaje),
          motivo: textoDetalle(d.motivo),
          ayuda: textoDetalle(d.ayuda),
          detalle: d.detalle,
          salida: d.salida,
        } }))
      } else {
        setForm(s => ({ ...s, resultado: { ok: false,
          mensaje: mensajeError(t('accion.subir_algoritmo'), textoDetalle(d), t) } }))
      }
    } catch (err) {
      setForm(s => ({ ...s, resultado: { ok: false, mensaje: mensajeError(t('accion.subir_algoritmo'), err, t) } }))
    } finally {
      setForm(s => ({ ...s, cargando: false }))
    }
  }

  const r = form.resultado
  const interfaz = form.interfaz

  // Cambios sobre la interfaz: cada uno deja de enseñar el resultado anterior.
  const cambiarInterfaz = (cambio) =>
    setForm(s => ({ ...s, interfaz: { ...s.interfaz, ...cambio(s.interfaz) }, resultado: null }))
  const cambiarFila = (lista, i, campo, valor) => cambiarInterfaz(f => ({
    [lista]: f[lista].map((fila, j) => (j === i ? { ...fila, [campo]: valor } : fila)),
  }))
  const quitarFila = (lista, i) => cambiarInterfaz(f => ({ [lista]: f[lista].filter((_, j) => j !== i) }))

  return (
    <div className="seccion-wrapper algoritmos-pagina">
      <h2>{t('algoritmos.titulo')}</h2>
      <p className="seccion-subtitulo">{t('algoritmos.subtitulo')}</p>

      <section className="panel panel-algoritmo">
        <form onSubmit={registrarAlgoritmo} className="formulario">
          <fieldset className="tipos-algoritmo">
            <legend>{t('algoritmos.que_hace')}</legend>
            {TIPOS.map(tipo => {
              const { familia, icono } = tipoNodo(tipo.valor)
              return (
                <label key={tipo.valor} className={`tipo-algoritmo familia-${familia}`}>
                  <input
                    type="radio"
                    name="tipo"
                    value={tipo.valor}
                    checked={form.tipo === tipo.valor}
                    onChange={() => setForm(s => ({
                      ...s, tipo: tipo.valor, interfaz: interfazPorDefecto(tipo.valor, t), resultado: null,
                    }))}
                  />
                  <Icono nombre={icono} tamano={20} />
                  {t(tipo.etiqueta)}
                </label>
              )
            })}
          </fieldset>

          <p className={`tipo-resumen familia-${tipoNodo(tipoActual.valor).familia}`}>
            {t(tipoActual.resumen)}
          </p>

          <fieldset className="interfaz-algoritmo">
            <legend>{t('algoritmos.como_se_llama')}</legend>

            <p className="interfaz-titulo">{t('algoritmos.entradas')}</p>
            <p className="texto-secundario">{t('algoritmos.entradas_texto')}</p>
            {interfaz.entradas.map((entrada, i) => (
              <div className="fila-interfaz" key={i}>
                <span className="fila-numero">{i + 1}</span>
                <input
                  aria-label={t('algoritmos.nombre_entrada', { n: i + 1 })}
                  value={entrada.nombre}
                  maxLength={40}
                  required
                  onChange={e => cambiarFila('entradas', i, 'nombre', e.target.value)}
                />
                <select
                  aria-label={t('algoritmos.clase_entrada', { n: i + 1 })}
                  value={entrada.clase}
                  onChange={e => cambiarFila('entradas', i, 'clase', e.target.value)}
                >
                  <option value="molecula">{t('tabla.molecula')}</option>
                  <option value="proteina">{t('algoritmos.proteina')}</option>
                </select>
                <button type="button" className="btn-enlace" disabled={interfaz.entradas.length === 1}
                        aria-label={t('algoritmos.quitar_entrada', { n: i + 1 })} onClick={() => quitarFila('entradas', i)}>
                  {t('algoritmos.quitar')}
                </button>
              </div>
            ))}
            <button type="button" className="btn-secundario btn-anadir"
                    disabled={interfaz.entradas.length >= MAX_ENTRADAS}
                    onClick={() => cambiarInterfaz(f => ({
                      entradas: [...f.entradas, { nombre: t('algoritmos.entrada_n', { n: f.entradas.length + 1 }), clase: 'molecula' }],
                    }))}>
              <Icono nombre="mas" />{t('algoritmos.anadir_entrada')}
            </button>

            <p className="interfaz-titulo">{t('algoritmos.salida_se_recibe')}</p>
            <div className="opciones-salida">
              <label>
                <input type="radio" name="salida" checked={!interfaz.opcion_salida}
                       onChange={() => cambiarInterfaz(() => ({ opcion_salida: null }))} />
                {t('algoritmos.ultimo_argumento')}
              </label>
              <label>
                <input type="radio" name="salida" checked={!!interfaz.opcion_salida}
                       onChange={() => cambiarInterfaz(() => ({ opcion_salida: '-o' }))} />
                {t('algoritmos.con_opcion')}
              </label>
              {interfaz.opcion_salida !== null && (
                <input
                  aria-label={t('algoritmos.opcion_salida')}
                  className="campo-opcion"
                  value={interfaz.opcion_salida}
                  maxLength={32}
                  required
                  onChange={e => cambiarInterfaz(() => ({ opcion_salida: e.target.value }))}
                />
              )}
            </div>

            <p className="interfaz-titulo">{t('algoritmos.opciones')}</p>
            <p className="texto-secundario">{t('algoritmos.opciones_texto')}</p>
            {interfaz.opciones.map((opcion, i) => (
              <div className="fila-interfaz" key={i}>
                <input
                  aria-label={t('algoritmos.opcion_n', { n: i + 1 })}
                  className="campo-opcion"
                  placeholder="--all"
                  value={opcion.opcion}
                  maxLength={32}
                  onChange={e => cambiarFila('opciones', i, 'opcion', e.target.value)}
                />
                <input
                  aria-label={t('algoritmos.que_hace_opcion', { n: i + 1 })}
                  placeholder={t('algoritmos.que_hace_ejemplo')}
                  value={opcion.nombre}
                  maxLength={40}
                  onChange={e => cambiarFila('opciones', i, 'nombre', e.target.value)}
                />
                <button type="button" className="btn-enlace" aria-label={t('algoritmos.quitar_opcion', { n: i + 1 })}
                        onClick={() => quitarFila('opciones', i)}>
                  {t('algoritmos.quitar')}
                </button>
              </div>
            ))}
            <button type="button" className="btn-secundario btn-anadir"
                    disabled={interfaz.opciones.length >= MAX_OPCIONES}
                    onClick={() => cambiarInterfaz(f => ({ opciones: [...f.opciones, { opcion: '', nombre: '' }] }))}>
              <Icono nombre="mas" />{t('algoritmos.anadir_opcion')}
            </button>

            <p className="vista-previa-llamada">
              {t('algoritmos.se_llamara')} <code>{vistaPreviaLlamada(form.archivo?.name, interfazParaEnviar(interfaz), t)}</code>
            </p>
          </fieldset>

          <label htmlFor="algoritmo-nombre">{t('algoritmos.nombre')}</label>
          <input
            id="algoritmo-nombre"
            placeholder={t('algoritmos.nombre_ejemplo')}
            value={form.nombre}
            onChange={e => setForm(s => ({ ...s, nombre: e.target.value }))}
            required
          />

          <label htmlFor="algoritmo-descripcion">{t('algoritmos.descripcion')}</label>
          <input
            id="algoritmo-descripcion"
            placeholder={t('algoritmos.descripcion_ejemplo')}
            value={form.descripcion}
            onChange={e => setForm(s => ({ ...s, descripcion: e.target.value }))}
            required
          />

          <label htmlFor="algoritmo-fichero">{t('algoritmos.script')}</label>
          <SelectorFichero
            id="algoritmo-fichero"
            accept=".py"
            fichero={form.archivo}
            alElegir={archivo => setForm(s => ({ ...s, archivo, resultado: null }))}
          />

          <button type="submit" className="btn-primary" disabled={form.cargando}>
            <Icono nombre={form.cargando ? 'procesando' : 'subir'} />
            {form.cargando ? t('algoritmos.validando') : t('algoritmos.subir_validar')}
          </button>
        </form>

        {form.cargando && (
          <p className="texto-secundario" role="status">
            {t('algoritmos.ejecutando')}
          </p>
        )}

        {r && r.ok && (
          <div className="exito-msg" role="status">
            <strong>{t('algoritmos.aceptado', { nombre: r.nombre })}</strong>
            <p>
              {t('algoritmos.devuelve')} <strong>{t(r.formato === 'json' ? 'algoritmos.devuelve_json' : 'algoritmos.devuelve_moleculas')}</strong>
              {r.clave && <>{t('algoritmos.puntuacion_de')} <code>{r.clave}</code></>}.
            </p>
            <p>{t('algoritmos.se_llamara')} <code>{r.llamada}</code></p>
          </div>
        )}

        {r && !r.ok && (
          <div className="error-msg" role="status">
            <strong>{r.mensaje || t('algoritmos.no_se_pudo')}</strong>
            {r.motivo && <p>{r.motivo}</p>}
            {r.ayuda && <p>{r.ayuda}</p>}

            {(r.detalle || r.salida) && (
              <details className="detalles-tecnicos">
                <summary>{t('algoritmos.detalles')}</summary>
                {r.detalle && (
                  <>
                    <p>{t('algoritmos.devolvio')}</p>
                    <pre>{r.detalle}</pre>
                  </>
                )}
                {r.salida && (
                  <>
                    <p>{t('algoritmos.consola')}</p>
                    <pre>{r.salida}</pre>
                  </>
                )}
              </details>
            )}
          </div>
        )}
      </section>
    </div>
  )
}
