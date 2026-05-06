import { useState } from 'react'

export default function Algoritmos({ usuario }) {
  const [nombre, setNombre] = useState('');
  const [descripcion, setDescripcion] = useState('');
  const [archivo, setArchivo] = useState(null);
  const [mensaje, setMensaje] = useState('');

  const registrarAlgoritmo = async (e) => {
    e.preventDefault();
    if (!archivo) { setMensaje("Error: Sube un archivo .py"); return; }

    const formData = new FormData();
    formData.append('nombre', nombre);
    formData.append('descripcion', descripcion);
    formData.append('autor_id', usuario.id);
    formData.append('es_publico', true);
    formData.append('archivo', archivo);

    const resp = await fetch('http://localhost:8000/algoritmos', { method: 'POST', body: formData });
    if (resp.ok) {
      setMensaje('✅ Algoritmo instalado correctamente');
      setNombre(''); setDescripcion(''); setArchivo(null);
    } else {
      const err = await resp.json();
      setMensaje(`❌ Error: ${err.detail || 'Fallo al subir'}`);
    }
  };

  return (
    <div className="seccion-wrapper">
      <h2>Subir Nuevo Algoritmo</h2>
      <p className="seccion-subtitulo">Registra un script .py que procese moléculas en la plataforma.</p>
      <form onSubmit={registrarAlgoritmo} className="formulario">
        <label>Nombre del algoritmo</label>
        <input placeholder="Ej: centerMol" value={nombre} onChange={e => setNombre(e.target.value)} required />
        <label>Descripción</label>
        <input placeholder="Qué hace este algoritmo..." value={descripcion} onChange={e => setDescripcion(e.target.value)} required />
        <label>Script de Python (.py)</label>
        <input type="file" accept=".py" onChange={e => setArchivo(e.target.files[0])} required />
        <button type="submit" className="btn-primary">Subir e Instalar</button>
      </form>
      {mensaje && <p className={mensaje.startsWith('✅') ? 'exito-msg' : 'error-msg'}>{mensaje}</p>}
    </div>
  );
}