import React, { useState } from 'react';
import { Handle, Position } from 'reactflow';
import { apiFetch } from '../../api/client';
import MarcoNodo from './MarcoNodo';
import Icono from '../Icono';
import { errorDeRespuesta, mensajeError } from '../../utils/mensajes';

const UploadNodoNode = ({ data, id }) => {
  const [archivo, setArchivo] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [nombreSubido, setNombreSubido] = useState(data.nombre_archivo || null);
  // Error dentro del propio nodo, junto a lo que lo ha causado (antes, alert).
  const [error, setError] = useState(null);

  const EXTENSIONES = ['.mol2', '.sdf', '.mol', '.pdb', '.pdbqt', '.smi', '.xyz'];

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setError(null);
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    if (EXTENSIONES.includes(ext)) {
      // El nombre definitivo no se conoce hasta que el servidor responde
      // (puede renombrar si ya existe), asi que aqui solo se guarda el
      // fichero elegido.
      setArchivo(file);
    } else {
      setArchivo(null);
      setError(`Ese formato no se admite. Usa uno de estos: ${EXTENSIONES.join(', ')}.`);
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
    setCargando(true);
    setError(null);
    const formData = new FormData();
    formData.append('archivo', archivo);
    formData.append('tipo', 'molecula');
    try {
      const response = await apiFetch('/moleculas/subir', { method: 'POST', body: formData });
      if (!response.ok) throw await errorDeRespuesta(response);
      const result = await response.json();
      // El servidor puede haber renombrado el fichero si el nombre ya
      // estaba ocupado, así que se guarda el que devuelve, no el local. La
      // confirmación es la línea con el nombre subido.
      data.nombre_archivo = result.nombre;
      setNombreSubido(result.nombre);
      setArchivo(null);
    } catch (err) {
      setError(mensajeError('subir la molécula', err));
    } finally {
      setCargando(false);
    }
  };

  return (
    <MarcoNodo id={id} tipo="upload" data={data}>
      <div className="nodo-body">
        <input type="file" accept=".mol2,.sdf,.mol,.pdb,.pdbqt,.smi,.xyz" onChange={handleFileChange}
               className="file-input" aria-label="Fichero de la molécula" />
        {nombreSubido && !archivo && (
          <p className="file-name"><Icono nombre="ok" tamano={12} />Subida: {nombreSubido}</p>
        )}
        {error && <p className="nodo-aviso" role="status">{error}</p>}
        <button onClick={uploadMolecula} disabled={!archivo || cargando} className="upload-btn">
          {cargando ? 'Subiendo…' : 'Subir'}
        </button>
      </div>
      <Handle type="source" position={Position.Right} id="output" />
    </MarcoNodo>
  );
};

export default UploadNodoNode;
