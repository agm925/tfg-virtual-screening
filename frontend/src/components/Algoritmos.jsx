import { useState } from 'react'
import { apiFetch } from '../api/client'

// Un único formulario con un selector de tipo, en lugar de los cuatro
// formularios separados que había antes.
//
// El cambio no es solo de presentación: el tipo que elige el autor es lo que
// le dice al banco de pruebas CÓMO invocar el algoritmo --una molécula, dos, o
// ligando más receptor-- antes de aceptarlo. Con cuatro formularios, elegir el
// equivocado se traducía en un mensaje de "el tipo no coincide"; ahora es un
// campo explícito y la plataforma verifica que la declaración sea cierta.
const TIPOS = [
  {
    valor: 'preprocesado',
    etiqueta: '⚗️ Preprocesado',
    resumen: 'Prepara o filtra una molécula: conversión de formato, hidrógenos, 3D, reglas de Lipinski.',
    entradas: 'Recibe 1 molécula.',
    color: '#e67e22',
  },
  {
    valor: 'alineacion',
    etiqueta: '📐 Alineación',
    resumen: 'Reorienta una molécula en el espacio, con o sin una referencia.',
    entradas: 'Recibe 1 molécula (y opcionalmente una de referencia).',
    color: '#3498db',
  },
  {
    valor: 'comparacion',
    etiqueta: '⚖️ Comparación',
    resumen: 'Compara dos moléculas y devuelve una métrica (similitud, RMSD) o una molécula alineada.',
    entradas: 'Recibe 2 moléculas.',
    color: '#e74c3c',
  },
  {
    valor: 'docking',
    etiqueta: '🔬 Docking',
    resumen: 'Acopla un ligando sobre un receptor y devuelve las poses generadas.',
    entradas: 'Recibe 1 ligando y 1 receptor.',
    color: '#8e44ad',
  },
]

const estadoInicial = {
  nombre: '', descripcion: '', tipo: 'preprocesado', archivo: null,
  cargando: false, resultado: null,
}

export default function Algoritmos() {
  const [form, setForm] = useState(estadoInicial)
  const tipoActual = TIPOS.find(t => t.valor === form.tipo)

  const registrarAlgoritmo = async (e) => {
    e.preventDefault()
    if (!form.archivo) {
      setForm(s => ({ ...s, resultado: { ok: false, motivo: 'Selecciona un archivo .py' } }))
      return
    }
    setForm(s => ({ ...s, cargando: true, resultado: null }))

    const formData = new FormData()
    formData.append('nombre', form.nombre)
    formData.append('descripcion', form.descripcion)
    formData.append('tipo', form.tipo)
    formData.append('es_publico', true)
    formData.append('archivo', form.archivo)

    try {
      const resp = await apiFetch('/algoritmos', { method: 'POST', body: formData })
      const datos = await resp.json()

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
        return
      }

      // 422 = no ha superado el banco de pruebas. El backend devuelve un
      // objeto con motivo, detalle y la salida del script: se muestra entero,
      // porque es lo que el autor necesita para arreglarlo.
      const d = datos.detail
      if (resp.status === 422 && d && typeof d === 'object') {
        setForm(s => ({ ...s, resultado: { ok: false, ...d } }))
      } else {
        setForm(s => ({ ...s, resultado: { ok: false,
          motivo: typeof d === 'string' ? d : 'No se pudo subir el algoritmo.' } }))
      }
    } catch (error) {
      setForm(s => ({ ...s, resultado: { ok: false, motivo: `Error de conexión: ${error.message}` } }))
    } finally {
      setForm(s => ({ ...s, cargando: false }))
    }
  }

  const r = form.resultado

  return (
    <div className="seccion-wrapper">
      <h2>Subir un algoritmo</h2>
      <p className="seccion-subtitulo">
        El script se ejecuta sobre dos moléculas de referencia antes de aceptarlo.
        Si falla, no se añade al catálogo y verás aquí el motivo.
      </p>

      {/* .seccion-wrapper no centra su contenido -- es un panel a ancho
          completo --, así que un bloque con maxWidth se queda pegado al
          borde izquierdo en vez de quedar en medio de la página. margin
          left/right auto es lo que lo centra; marginTop no puede ir en el
          shorthand `margin` sin repetirlo, así que se deja aparte. */}
      <form onSubmit={registrarAlgoritmo} className="formulario"
            style={{ maxWidth: 640, marginTop: '1.5rem', marginLeft: 'auto', marginRight: 'auto' }}>

        <label>¿Qué hace el algoritmo?</label>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 8 }}>
          {TIPOS.map(t => (
            <button
              type="button"
              key={t.valor}
              onClick={() => setForm(s => ({ ...s, tipo: t.valor, resultado: null }))}
              style={{
                padding: '10px 8px', cursor: 'pointer', fontSize: '0.9rem',
                borderRadius: 6, textAlign: 'left',
                // Explícito: sin color propio, un botón hereda el color de
                // sistema `buttontext`, que con el `color-scheme: light dark`
                // de index.css es BLANCO si el sistema operativo está en modo
                // oscuro, y estas tarjetas tienen el fondo blanco.
                color: '#2c3e50',
                border: form.tipo === t.valor ? `2px solid ${t.color}` : '1px solid #ccc',
                background: form.tipo === t.valor ? `${t.color}18` : 'white',
                fontWeight: form.tipo === t.valor ? 600 : 400,
              }}
            >
              {t.etiqueta}
            </button>
          ))}
        </div>

        <p style={{
          fontSize: '0.85rem', color: '#555', background: '#f6f8f9',
          borderLeft: `3px solid ${tipoActual.color}`, padding: '10px 12px',
          margin: '10px 0 4px', borderRadius: '0 4px 4px 0',
        }}>
          {tipoActual.resumen}<br />
          <strong>{tipoActual.entradas}</strong> El resultado se escribe en el <strong>último</strong> argumento
          de la línea de comandos.
        </p>

        <label>Nombre del algoritmo</label>
        <input
          placeholder="Ej: Filtro de Lipinski"
          value={form.nombre}
          onChange={e => setForm(s => ({ ...s, nombre: e.target.value }))}
          required
        />

        <label>Descripción</label>
        <input
          placeholder="Qué hace este algoritmo..."
          value={form.descripcion}
          onChange={e => setForm(s => ({ ...s, descripcion: e.target.value }))}
          required
        />

        <label>Script de Python (.py)</label>
        <input
          type="file"
          accept=".py"
          onChange={e => setForm(s => ({ ...s, archivo: e.target.files[0], resultado: null }))}
          required
        />

        <button type="submit" className="btn-primary" disabled={form.cargando}>
          {form.cargando ? 'Validando el algoritmo…' : 'Subir y validar'}
        </button>
      </form>

      {form.cargando && (
        <p style={{ marginTop: '1rem', color: '#555' }}>
          Ejecutando el algoritmo sobre las moléculas de referencia. Puede tardar unos segundos.
        </p>
      )}

      {r && r.ok && (
        <div style={{
          marginTop: '1.5rem', maxWidth: 640, padding: '1rem 1.25rem',
          marginLeft: 'auto', marginRight: 'auto',
          background: '#d5f4e6', color: '#1e6b45', borderRadius: 6,
        }}>
          <strong>✅ «{r.nombre}» superó la validación y ya está en el catálogo.</strong>
          <p style={{ margin: '8px 0 0', fontSize: '0.9rem' }}>
            Formato de salida detectado: <strong>{r.formato === 'json' ? 'métricas (JSON)' : 'molécula'}</strong>
            {r.clave && <> · puntuación en <code>{r.clave}</code></>}
          </p>
        </div>
      )}

      {r && !r.ok && (
        <div style={{
          marginTop: '1.5rem', maxWidth: 640, padding: '1rem 1.25rem',
          marginLeft: 'auto', marginRight: 'auto',
          background: '#fadbd8', color: '#922b21', borderRadius: 6,
        }}>
          <strong>❌ {r.mensaje || 'No se pudo subir el algoritmo'}</strong>
          {r.motivo && <p style={{ margin: '8px 0 0' }}>{r.motivo}</p>}

          {r.detalle && (
            <>
              <p style={{ margin: '12px 0 4px', fontWeight: 600, fontSize: '0.85rem' }}>
                Lo que devolvió el script:
              </p>
              <pre style={{
                background: '#fff', color: '#5b1a14', padding: '8px 10px',
                borderRadius: 4, fontSize: '0.78rem', overflowX: 'auto',
                maxHeight: 200, whiteSpace: 'pre-wrap',
              }}>{r.detalle}</pre>
            </>
          )}

          {r.salida && (
            <>
              <p style={{ margin: '12px 0 4px', fontWeight: 600, fontSize: '0.85rem' }}>
                Salida por consola:
              </p>
              <pre style={{
                background: '#fff', color: '#5b1a14', padding: '8px 10px',
                borderRadius: 4, fontSize: '0.78rem', overflowX: 'auto',
                maxHeight: 160, whiteSpace: 'pre-wrap',
              }}>{r.salida}</pre>
            </>
          )}

          {r.ayuda && (
            <p style={{ margin: '12px 0 0', fontSize: '0.85rem', fontStyle: 'italic' }}>
              {r.ayuda}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
