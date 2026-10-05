import React, { useState } from 'react';
import { Handle, Position } from 'reactflow';
import { apiFetch } from '../../api/client';
import MarcoNodo from './MarcoNodo';

const UploadNodoNode = ({ data, id }) => {
  const [archivo, setArchivo] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [nombreSubido, setNombreSubido] = useState(data.nombre_archivo || null);

  const EXTENSIONES = ['.mol2', '.sdf', '.mol', '.pdb', '.pdbqt', '.smi', '.xyz'];

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    if (EXTENSIONES.includes(ext)) {
      // El nombre definitivo no se conoce hasta que el servidor responde
      // (puede renombrar si ya existe), asi que aqui solo se guarda el
      // fichero elegido.
      setArchivo(file);
    } else {
      alert(`Formato no soportado. Usa: ${EXTENSIONES.join(', ')}`);
    }
  };

  // Sube el fichero a la biblioteca y lo publica al grafo.
  //
  // Antes esto llamaba a POST /peticiones con `algoritmo_id: 1` fijo en el
  // código, lo que no era "añadir un archivo al flujo": creaba una petición
  // real y ENCOLABA UN TRABAJO que ejecutaba el algoritmo número 1 sobre la
  // molécula, sin que el usuario lo hubiera pedido. Y si ese id no existía en
  // el catálogo, la tarea moría con un error incomprensible.
  //
  // El endpoint correcto es /moleculas/subir, que es justamente lo que este
  // nodo necesita: dejar el fichero disponible para los nodos siguientes.
  const uploadMolecula = async () => {
    if (!archivo) { alert('Selecciona un archivo primero'); return; }
    setCargando(true);
    const formData = new FormData();
    formData.append('archivo', archivo);
    formData.append('tipo', 'molecula');
    try {
      const response = await apiFetch('/moleculas/subir', { method: 'POST', body: formData });
      const result = await response.json();
      if (response.ok) {
        // El servidor puede haber renombrado el fichero si el nombre ya
        // estaba ocupado, así que se guarda el que devuelve, no el local.
        data.nombre_archivo = result.nombre;
        setNombreSubido(result.nombre);
        alert(`"${result.nombre}" subido correctamente`);
      } else {
        alert(result.detail || 'Error cargando archivo');
      }
    } catch (err) {
      alert('Error: ' + err.message);
    } finally {
      setCargando(false);
    }
  };

  return (
    <MarcoNodo id={id} tipo="upload">
      <div className="nodo-body">
        <input type="file" accept=".mol2,.sdf,.mol,.pdb,.pdbqt,.smi,.xyz" onChange={handleFileChange} className="file-input" />
        {archivo && !nombreSubido && <p className="file-name">{archivo.name}</p>}
        {nombreSubido && <p className="file-name">✓ {nombreSubido}</p>}
        <button onClick={uploadMolecula} disabled={!archivo || cargando} className="upload-btn">
          {cargando ? 'Cargando...' : 'Cargar'}
        </button>
      </div>
      <Handle type="source" position={Position.Right} id="output" />
    </MarcoNodo>
  );
};

export default UploadNodoNode;
