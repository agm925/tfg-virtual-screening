import { useState } from 'react'
import { apiFetch } from '../api/client'
import Icono from './Icono'
import { tipoNodo, ETIQUETA_ALGORITMO } from '../utils/tiposNodo'
import { mensajeError, textoDetalle } from '../utils/mensajes'
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
// en el nodo Docking.
const TIPOS = [
  {
    valor: 'preprocesado',
    etiqueta: ETIQUETA_ALGORITMO.preprocesado,
    resumen: 'Prepara o filtra una molécula: conversión de formato, hidrógenos, 3D, reglas de Lipinski.',
    entradas: 'Recibe 1 molécula.',
  },
  {
    valor: 'alineacion',
    etiqueta: ETIQUETA_ALGORITMO.alineacion,
    resumen: 'Reorienta una molécula en el espacio, con o sin una referencia.',
    entradas: 'Recibe 1 molécula (y opcionalmente una de referencia).',
  },
  {
    valor: 'comparacion',
    etiqueta: ETIQUETA_ALGORITMO.comparacion,
    resumen: 'Compara dos moléculas y devuelve una métrica (similitud, RMSD) o una molécula alineada.',
    entradas: 'Recibe 2 moléculas.',
  },
  {
    valor: 'docking',
    etiqueta: ETIQUETA_ALGORITMO.docking,
    resumen: 'Acopla un ligando sobre un receptor y devuelve las poses generadas.',
    entradas: 'Recibe 1 ligando y 1 receptor.',
  },
]

const estadoInicial = {
  nombre: '', descripcion: '', tipo: 'preprocesado', archivo: null,
  cargando: false, resultado: null,
}

export default function Algoritmos() {
  const [form, setForm] = useState(estadoInicial)
  // Se cambia al subir uno bien, para vaciar el <input type="file">, que no
  // se puede controlar desde el estado.
  const [claveFichero, setClaveFichero] = useState(0)
  const tipoActual = TIPOS.find(t => t.valor === form.tipo)

  const registrarAlgoritmo = async (e) => {
    e.preventDefault()
    setForm(s => ({ ...s, cargando: true, resultado: null }))

    const formData = new FormData()
    formData.append('nombre', form.nombre)
    formData.append('descripcion', form.descripcion)
    formData.append('tipo', form.tipo)
    formData.append('es_publico', true)
    formData.append('archivo', form.archivo)

    try {
      const resp = await apiFetch('/algoritmos', { method: 'POST', body: formData })
      const datos = await resp.json().catch(() => ({}))

      if (resp.ok) {
        setForm({
          ...estadoInicial,
          tipo: form.tipo,
          resultado: {
            ok: true,
            nombre: datos.nombre,
            formato: datos.formato_salida,
            clave: datos.clave_score,
          },
        })
        setClaveFichero(k => k + 1)
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
          mensaje: mensajeError('subir el algoritmo', textoDetalle(d)) } }))
      }
    } catch (err) {
      setForm(s => ({ ...s, resultado: { ok: false, mensaje: mensajeError('subir el algoritmo', err) } }))
    } finally {
      setForm(s => ({ ...s, cargando: false }))
    }
  }

  const r = form.resultado

  return (
    <div className="seccion-wrapper algoritmos-pagina">
      <h2>Subir un algoritmo</h2>
      <p className="seccion-subtitulo">
        El script se ejecuta sobre dos moléculas de referencia antes de aceptarlo.
        Si falla, no se añade al catálogo y verás aquí el motivo.
      </p>

      <section className="panel panel-algoritmo">
        <form onSubmit={registrarAlgoritmo} className="formulario">
          <fieldset className="tipos-algoritmo">
            <legend>¿Qué hace el algoritmo?</legend>
            {TIPOS.map(t => {
              const { familia, icono } = tipoNodo(t.valor)
              return (
                <label key={t.valor} className={`tipo-algoritmo familia-${familia}`}>
                  <input
                    type="radio"
                    name="tipo"
                    value={t.valor}
                    checked={form.tipo === t.valor}
                    onChange={() => setForm(s => ({ ...s, tipo: t.valor, resultado: null }))}
                  />
                  <Icono nombre={icono} tamano={20} />
                  {t.etiqueta}
                </label>
              )
            })}
          </fieldset>

          <p className={`tipo-resumen familia-${tipoNodo(tipoActual.valor).familia}`}>
            {tipoActual.resumen}<br />
            <strong>{tipoActual.entradas}</strong> El resultado se escribe en el <strong>último</strong> argumento
            de la línea de comandos.
          </p>

          <label htmlFor="algoritmo-nombre">Nombre del algoritmo</label>
          <input
            id="algoritmo-nombre"
            placeholder="Ej: Filtro de Lipinski"
            value={form.nombre}
            onChange={e => setForm(s => ({ ...s, nombre: e.target.value }))}
            required
          />

          <label htmlFor="algoritmo-descripcion">Descripción</label>
          <input
            id="algoritmo-descripcion"
            placeholder="Qué hace este algoritmo…"
            value={form.descripcion}
            onChange={e => setForm(s => ({ ...s, descripcion: e.target.value }))}
            required
          />

          <label htmlFor="algoritmo-fichero">Script de Python (.py)</label>
          <input
            key={claveFichero}
            id="algoritmo-fichero"
            type="file"
            accept=".py"
            onChange={e => setForm(s => ({ ...s, archivo: e.target.files[0], resultado: null }))}
            required
          />

          <button type="submit" className="btn-primary" disabled={form.cargando}>
            <Icono nombre={form.cargando ? 'procesando' : 'subir'} />
            {form.cargando ? 'Validando el algoritmo…' : 'Subir y validar'}
          </button>
        </form>

        {form.cargando && (
          <p className="texto-secundario" role="status">
            Ejecutando el algoritmo sobre las moléculas de referencia. Puede tardar unos segundos.
          </p>
        )}

        {r && r.ok && (
          <div className="exito-msg" role="status">
            <strong>«{r.nombre}» ha superado la validación y ya está en el catálogo.</strong>
            <p>
              Devuelve <strong>{r.formato === 'json' ? 'resultados numéricos (JSON)' : 'moléculas'}</strong>
              {r.clave && <>; la puntuación se lee de <code>{r.clave}</code></>}.
            </p>
          </div>
        )}

        {r && !r.ok && (
          <div className="error-msg" role="status">
            <strong>{r.mensaje || 'No se pudo subir el algoritmo.'}</strong>
            {r.motivo && <p>{r.motivo}</p>}
            {r.ayuda && <p>{r.ayuda}</p>}

            {(r.detalle || r.salida) && (
              <details className="detalles-tecnicos">
                <summary>Detalles técnicos</summary>
                {r.detalle && (
                  <>
                    <p>Lo que devolvió el script:</p>
                    <pre>{r.detalle}</pre>
                  </>
                )}
                {r.salida && (
                  <>
                    <p>Salida por consola:</p>
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
