import React, { useState } from 'react';
import { Handle, Position } from 'reactflow';
import { apiFetch } from '../../api/client';
import MarcoNodo from './MarcoNodo';
import Icono from '../Icono';
import PreguntaVisibilidad from '../PreguntaVisibilidad';
import SelectorFichero from '../SelectorFichero';
import { errorDeRespuesta, mensajeError } from '../../utils/mensajes';
import { useIdioma } from '../../hooks/useIdioma';

const UploadNodoNode = ({ data, id }) => {
  const { t } = useIdioma();
  const [archivo, setArchivo] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [nombreSubido, setNombreSubido] = useState(data.nombre_archivo || null);
  // Error dentro del propio nodo, junto a lo que lo ha causado (antes, alert).
  const [error, setError] = useState(null);
  const [preguntando, setPreguntando] = useState(false);
  // Solo se sabe de lo subido en esta sesión del editor; al reabrir un
  // workflow guardado no se pinta nada en vez de adivinar.
  const [esPublico, setEsPublico] = useState(null);

  const EXTENSIONES = ['.mol2', '.sdf', '.mol', '.pdb', '.pdbqt', '.smi', '.xyz'];

  const handleFileChange = (file) => {
    setError(null);
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    if (EXTENSIONES.includes(ext)) {
      // El nombre definitivo no se conoce hasta que el servidor responde
      // (puede renombrar si ya existe), asi que aqui solo se guarda el
      // fichero elegido.
      setArchivo(file);
    } else {
      setArchivo(null);
      setError(t('nodos.formato_no_admitido', { formatos: EXTENSIONES.join(', ') }));
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
  //
  // Antes de subir se pregunta quién podrá verlo, igual que en Moléculas
  // (spec 007).
  const uploadMolecula = async (publico) => {
    setPreguntando(false);
    setCargando(true);
    setError(null);
    const formData = new FormData();
    formData.append('archivo', archivo);
    formData.append('tipo', 'molecula');
    formData.append('es_publico', publico ? 'true' : 'false');
    try {
      const response = await apiFetch('/moleculas/subir', { method: 'POST', body: formData });
      if (!response.ok) throw await errorDeRespuesta(response);
      const result = await response.json();
      // El servidor puede haber renombrado el fichero si el nombre ya
      // estaba ocupado, así que se guarda el que devuelve, no el local. La
      // confirmación es la línea con el nombre subido.
      data.nombre_archivo = result.nombre;
      setNombreSubido(result.nombre);
      setEsPublico(result.es_publico);
      setArchivo(null);
    } catch (err) {
      setError(mensajeError(t('accion.subir_molecula'), err, t));
    } finally {
      setCargando(false);
    }
  };

  return (
    <MarcoNodo id={id} tipo="upload" data={data}>
      <div className="nodo-body">
        <SelectorFichero id={`subir-${id}`} accept=".mol2,.sdf,.mol,.pdb,.pdbqt,.smi,.xyz"
                         fichero={archivo} alElegir={handleFileChange} className="en-nodo" />
        {nombreSubido && !archivo && (
          <p className="file-name">
            <Icono nombre="ok" tamano={12} />{t('nodos.subida', { nombre: nombreSubido })}
            {esPublico === false && ` ${t('nodos.privada')}`}
          </p>
        )}
        {error && <p className="nodo-aviso" role="status">{error}</p>}
        <button onClick={() => setPreguntando(true)} disabled={!archivo || cargando} className="upload-btn">
          {cargando ? t('moleculas.subiendo') : t('moleculas.subir')}
        </button>
        <PreguntaVisibilidad fichero={preguntando ? archivo?.name : null}
                             alElegir={uploadMolecula} alCancelar={() => setPreguntando(false)} />
      </div>
      <Handle type="source" position={Position.Right} id="output" />
    </MarcoNodo>
  );
};

export default UploadNodoNode;
