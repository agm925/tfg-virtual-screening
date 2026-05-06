import React, { useState } from 'react';
import { Handle, Position } from 'reactflow';
import '../../styles/Nodos.css';

const UploadNodoNode = ({ data, id }) => {
  const [archivo, setArchivo] = useState(null);
  const [cargando, setCargando] = useState(false);

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
    if (!archivo) {
      alert('Selecciona un archivo primero');
      return;
    }

    setCargando(true);
    const formData = new FormData();
    formData.append('archivo_mol', archivo);
    formData.append('usuario_id', 1); // TODO: obtener del contexto
    formData.append('algoritmo_id', 1);

    try {
      const response = await fetch('http://localhost:8000/peticiones', {
        method: 'POST',
        body: formData
      });

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
      <div className="nodo-header">📤 Upload Molécula</div>
      
      <div className="nodo-body">
        <input 
          type="file" 
          accept=".mol2" 
          onChange={handleFileChange}
          className="file-input"
        />
        
        {archivo && <p className="file-name">✓ {archivo.name}</p>}
        
        <button 
          onClick={uploadMolecula}
          disabled={!archivo || cargando}
          className="upload-btn"
        >
          {cargando ? 'Cargando...' : 'Cargar'}
        </button>
      </div>

      <Handle type="output" position={Position.Right} />
    </div>
  );
};

export default UploadNodoNode;
