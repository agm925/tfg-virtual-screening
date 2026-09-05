import React, { useState } from 'react';
import { Handle, Position, useReactFlow } from 'reactflow';
import { apiFetch } from '../../api/client';
import '../../styles/Nodos.css';

const UploadNodoNode = ({ data, id }) => {
  const { setNodes, setEdges } = useReactFlow();
  const [archivo, setArchivo] = useState(null);
  const [cargando, setCargando] = useState(false);

  const eliminar = (e) => {
    e.stopPropagation();
    setNodes(nds => nds.filter(n => n.id !== id));
    setEdges(eds => eds.filter(e => e.source !== id && e.target !== id));
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file && file.name.endsWith('.mol2')) {
      setArchivo(file);
      data.nombre_archivo = file.name;
    } else {
      alert('Por favor sube un archivo .mol2');
    }
  };

  const uploadMolecula = async () => {
    if (!archivo) { alert('Selecciona un archivo primero'); return; }
    setCargando(true);
    const formData = new FormData();
    formData.append('archivo_mol', archivo);
    formData.append('algoritmo_id', 1);
    try {
      const response = await apiFetch('/peticiones', { method: 'POST', body: formData });
      if (response.ok) {
        const result = await response.json();
        data.archivo_id = result.id;
        data.nombre_archivo = archivo.name;
        alert('Archivo cargado exitosamente');
      } else {
        alert('Error cargando archivo');
      }
    } catch (err) {
      alert('Error: ' + err.message);
    } finally {
      setCargando(false);
    }
  };

  return (
    <div className="nodo upload-nodo">
      <div className="nodo-header">
        📤 Upload Molécula
        <button className="nodo-btn-borrar" onClick={eliminar} title="Eliminar nodo">×</button>
      </div>
      <div className="nodo-body">
        <input type="file" accept=".mol2" onChange={handleFileChange} className="file-input" />
        {archivo && <p className="file-name">✓ {archivo.name}</p>}
        <button onClick={uploadMolecula} disabled={!archivo || cargando} className="upload-btn">
          {cargando ? 'Cargando...' : 'Cargar'}
        </button>
      </div>
      <Handle type="source" position={Position.Right} id="output" />
    </div>
  );
};

export default UploadNodoNode;
