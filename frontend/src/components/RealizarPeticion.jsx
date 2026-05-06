import { useState, useEffect } from 'react'

export default function RealizarPeticion({ usuario }) {
  const [peticiones, setPeticiones] = useState([]);
  const [algoritmos, setAlgoritmos] = useState([]);
  const [archivo, setArchivo] = useState(null);
  const [algoritmoSeleccionado, setAlgoritmoSeleccionado] = useState('');
  const [mensaje, setMensaje] = useState('');

  const cargarDatos = async () => {
    const respPet = await fetch(`http://localhost:8000/peticiones/usuario/${usuario.id}`);
    if (respPet.ok) setPeticiones(await respPet.json());

    const respAlg = await fetch('http://localhost:8000/algoritmos');
    if (respAlg.ok) {
      const data = await respAlg.json();
      setAlgoritmos(data);
      if (data.length > 0) setAlgoritmoSeleccionado(data[0].id);
    }
  };

  useEffect(() => { cargarDatos(); }, []);

  const subirMolecula = async (e) => {
    e.preventDefault();
    if (!algoritmoSeleccionado) { setMensaje("Selecciona un algoritmo primero"); return; }
    const formData = new FormData();
    formData.append('usuario_id', usuario.id);
    formData.append('algoritmo_id', algoritmoSeleccionado);
    formData.append('archivo_mol', archivo);
    const resp = await fetch('http://localhost:8000/peticiones', { method: 'POST', body: formData });
    if (resp.ok) { setMensaje('✅ Petición creada con éxito'); cargarDatos(); }
  };

  const ejecutarYDescargar = async (id) => {
    const resp = await fetch(`http://localhost:8000/ejecutar/${id}`, { method: 'POST' });
    if (resp.ok) { window.open(`http://localhost:8000/descargar/${id}`, '_blank'); cargarDatos(); }
  };

  const borrarPeticion = async (id) => {
    if (!confirm("¿Seguro que quieres eliminar esta petición?")) return;
    const resp = await fetch(`http://localhost:8000/peticiones/${id}`, { method: 'DELETE' });
    if (resp.ok) cargarDatos();
  };

  return (
    <div className="seccion-wrapper">
      <h2>Realizar Petición</h2>
      <form onSubmit={subirMolecula} className="formulario">
        <label>Algoritmo a ejecutar</label>
        <select value={algoritmoSeleccionado} onChange={e => setAlgoritmoSeleccionado(e.target.value)} required>
          {algoritmos.length === 0
            ? <option value="">No hay algoritmos disponibles</option>
            : algoritmos.map(alg => <option key={alg.id} value={alg.id}>{alg.nombre}</option>)
          }
        </select>
        <label>Molécula (.mol2)</label>
        <input type="file" accept=".mol2" onChange={e => setArchivo(e.target.files[0])} required />
        <button type="submit" className="btn-primary verde">Subir Molécula</button>
      </form>
      {mensaje && <p className="exito-msg">{mensaje}</p>}

      <h3 style={{ marginTop: '40px' }}>Historial de Peticiones</h3>
      <table className="tabla-peticiones">
        <thead>
          <tr><th>ID</th><th>Archivo</th><th>Estado</th><th>Acciones</th></tr>
        </thead>
        <tbody>
          {peticiones.map(p => (
            <tr key={p.id}>
              <td>{p.id}</td>
              <td>{p.ruta_mol_original}</td>
              <td><span className={`badge ${p.estado.toLowerCase()}`}>{p.estado}</span></td>
              <td className="acciones-celda">
                <button onClick={() => ejecutarYDescargar(p.id)} className="btn-ejecutar">
                  {p.estado === 'COMPLETADO' ? 'Re-descargar' : 'Ejecutar'}
                </button>
                <button onClick={() => borrarPeticion(p.id)} className="btn-borrar">Borrar</button>
              </td>
            </tr>
          ))}
          {peticiones.length === 0 && (
            <tr><td colSpan="4" className="tabla-vacia">No hay simulaciones previas</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}