import { useState } from 'react'
import { apiFetch } from '../api/client'

// Definido FUERA del componente padre para que React no lo desmonte en cada render
function FormularioAlgoritmo({ tipo, titulo, color, estado, set, onSubmit }) {
  return (
    <div className="formulario-contenedor">
      <h3 style={{ borderBottom: `2px solid ${color}`, paddingBottom: '0.5rem', marginBottom: '1rem' }}>
        {titulo}
      </h3>
      <form onSubmit={(e) => onSubmit(e, tipo, estado)} className="formulario">
        <label>Nombre del algoritmo</label>
        <input
          placeholder={`Ej: ${tipo === 'alineacion' ? 'centerMol' : tipo === 'comparacion' ? 'Tanimoto' : tipo === 'preprocesado' ? 'preparacionObabel' : 'dockingSmina'}`}
          value={estado.nombre}
          onChange={e => set(s => ({ ...s, nombre: e.target.value }))}
          required
        />
        <label>Descripción</label>
        <input
          placeholder="Qué hace este algoritmo..."
          value={estado.descripcion}
          onChange={e => set(s => ({ ...s, descripcion: e.target.value }))}
          required
        />
        <label>Script de Python (.py)</label>
        <input
          type="file"
          accept=".py"
          onChange={e => set(s => ({ ...s, archivo: e.target.files[0] }))}
          required
        />
        <p style={{ fontSize: '0.85rem', color: '#7f8c8d', marginTop: '0.5rem' }}>
          ℹ️ El script debe incluir: <code># TIPO_ALGORITMO: {tipo}</code>
        </p>
        <button type="submit" className="btn-primary" disabled={estado.cargando}>
          {estado.cargando ? 'Subiendo...' : 'Subir e Instalar'}
        </button>
      </form>
      {estado.mensaje && (
        <p style={{
          marginTop: '1rem', padding: '0.75rem', borderRadius: '4px', whiteSpace: 'pre-wrap',
          backgroundColor: estado.mensaje.startsWith('✅') ? '#d5f4e6' : '#fadbd8',
          color:           estado.mensaje.startsWith('✅') ? '#27ae60' : '#c0392b',
        }}>
          {estado.mensaje}
        </p>
      )}
    </div>
  );
}

const crearEstado = () => ({
  nombre: '', descripcion: '', archivo: null, mensaje: '', cargando: false,
});

export default function Algoritmos({ usuario }) {
  const [alineacion,   setAlineacion]   = useState(crearEstado());
  const [comparacion,  setComparacion]  = useState(crearEstado());
  const [preprocesado, setPreprocesado] = useState(crearEstado());
  const [docking,      setDocking]      = useState(crearEstado());

  const setters = {
    alineacion:   setAlineacion,
    comparacion:  setComparacion,
    preprocesado: setPreprocesado,
    docking:      setDocking,
  };

  const registrarAlgoritmo = async (e, tipo, estado) => {
    e.preventDefault();
    const set = setters[tipo];
    set(s => ({ ...s, cargando: true, mensaje: '' }));

    if (!estado.archivo) {
      set(s => ({ ...s, cargando: false, mensaje: '❌ Error: Sube un archivo .py' }));
      return;
    }

    const formData = new FormData();
    formData.append('nombre',      estado.nombre);
    formData.append('descripcion', estado.descripcion);
    formData.append('tipo',        tipo);
    formData.append('es_publico',  true);
    formData.append('archivo',     estado.archivo);

    try {
      const resp = await apiFetch('/algoritmos', {
        method: 'POST',
        body: formData,
      });

      if (resp.ok) {
        set(s => ({ ...s, mensaje: `✅ Algoritmo de ${tipo} instalado correctamente` }));
        set(s => ({ ...s, nombre: '', descripcion: '', archivo: null }));
      } else {
        const err    = await resp.json();
        const detail = err.detail || 'Fallo al subir';
        if (resp.status === 403) {
          set(s => ({ ...s, mensaje: `❌ Tu rol (${usuario.rol}) no tiene permiso para subir algoritmos al catálogo. Solo admin o desarrollador.` }));
        } else if (detail.includes('no coincide')) {
          const sugerido = detail.match(/'(\w+)'\)/)?.[1] || tipo;
          set(s => ({ ...s, mensaje: `❌ ${detail}\n\nℹ️ Súbelo en el formulario de '${sugerido}'` }));
        } else {
          set(s => ({ ...s, mensaje: `❌ Error: ${detail}` }));
        }
      }
    } catch (error) {
      set(s => ({ ...s, mensaje: `❌ Error de conexión: ${error.message}` }));
    } finally {
      set(s => ({ ...s, cargando: false }));
    }
  };

  return (
    <div className="seccion-wrapper">
      <h2>Subir Nuevos Algoritmos</h2>
      <p className="seccion-subtitulo">Registra scripts .py que procesen moléculas en la plataforma.</p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem', marginTop: '2rem' }}>

        <FormularioAlgoritmo
          tipo="alineacion"
          titulo="📐 Algoritmo de Alineación"
          color="#3498db"
          estado={alineacion}
          set={setAlineacion}
          onSubmit={registrarAlgoritmo}
        />

        <FormularioAlgoritmo
          tipo="comparacion"
          titulo="⚖️ Algoritmo de Comparación"
          color="#e74c3c"
          estado={comparacion}
          set={setComparacion}
          onSubmit={registrarAlgoritmo}
        />

        <FormularioAlgoritmo
          tipo="preprocesado"
          titulo="⚗️ Algoritmo de Preprocesado"
          color="#e67e22"
          estado={preprocesado}
          set={setPreprocesado}
          onSubmit={registrarAlgoritmo}
        />

        <FormularioAlgoritmo
          tipo="docking"
          titulo="🔬 Algoritmo de Docking"
          color="#8e44ad"
          estado={docking}
          set={setDocking}
          onSubmit={registrarAlgoritmo}
        />

      </div>
    </div>
  );
}
