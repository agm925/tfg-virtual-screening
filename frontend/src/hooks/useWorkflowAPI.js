import { useState, useCallback } from 'react';

const API_BASE = 'http://localhost:8000';

const useWorkflowAPI = () => {
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState(null);

  // Crear workflow
  const crearWorkflow = useCallback(async (workflow, usuarioId) => {
    setCargando(true);
    try {
      const formData = new FormData();
      formData.append('nombre', workflow.nombre);
      formData.append('descripcion', workflow.descripcion);
      formData.append('usuario_id', usuarioId);

      const response = await fetch(`${API_BASE}/workflows`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) throw new Error('Error creando workflow');

      const data = await response.json();
      setError(null);
      return data;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setCargando(false);
    }
  }, []);

  // Obtener workflows del usuario
  const obtenerWorkflows = useCallback(async (usuarioId) => {
    setCargando(true);
    try {
      const response = await fetch(`${API_BASE}/workflows/usuario/${usuarioId}`);

      if (!response.ok) throw new Error('Error obteniendo workflows');

      const data = await response.json();
      setError(null);
      return data;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setCargando(false);
    }
  }, []);

  // Obtener workflow específico
  const obtenerWorkflow = useCallback(async (workflowId) => {
    setCargando(true);
    try {
      const response = await fetch(`${API_BASE}/workflows/${workflowId}`);

      if (!response.ok) throw new Error('Error obteniendo workflow');

      const data = await response.json();
      setError(null);
      return data;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setCargando(false);
    }
  }, []);

  // Actualizar workflow
  const actualizarWorkflow = useCallback(async (workflowId, workflow) => {
    setCargando(true);
    try {
      const response = await fetch(`${API_BASE}/workflows/${workflowId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nombre: workflow.nombre,
          descripcion: workflow.descripcion,
          grafo_json: workflow.grafo_json,
        }),
      });

      if (!response.ok) throw new Error('Error actualizando workflow');

      const data = await response.json();
      setError(null);
      return data;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setCargando(false);
    }
  }, []);

  // Ejecutar workflow
  const ejecutarWorkflow = useCallback(async (workflowId, usuarioId) => {
    setCargando(true);
    try {
      const formData = new FormData();
      formData.append('usuario_id', usuarioId);

      const response = await fetch(`${API_BASE}/workflows/${workflowId}/ejecutar`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Error ejecutando workflow');
      }

      const data = await response.json();
      setError(null);
      return data;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setCargando(false);
    }
  }, []);

  // Obtener ejecuciones de un workflow
  const obtenerEjecuciones = useCallback(async (workflowId) => {
    setCargando(true);
    try {
      const response = await fetch(`${API_BASE}/workflows/${workflowId}/ejecuciones`);

      if (!response.ok) throw new Error('Error obteniendo ejecuciones');

      const data = await response.json();
      setError(null);
      return data;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setCargando(false);
    }
  }, []);

  // Obtener detalles de ejecución
  const obtenerEjecucion = useCallback(async (ejecucionId) => {
    setCargando(true);
    try {
      const response = await fetch(`${API_BASE}/workflows/ejecuciones/${ejecucionId}`);

      if (!response.ok) throw new Error('Error obteniendo ejecución');

      const data = await response.json();
      setError(null);
      return data;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setCargando(false);
    }
  }, []);

  // Descargar resultado
  const descargarResultado = useCallback(async (nombreArchivo) => {
    try {
      window.location.href = `${API_BASE}/descargar?archivo=${nombreArchivo}`;
      setError(null);
    } catch (err) {
      setError(err.message);
      throw err;
    }
  }, []);

  // Borrar workflow
  const borrarWorkflow = useCallback(async (workflowId) => {
    setCargando(true);
    try {
      const response = await fetch(`${API_BASE}/workflows/${workflowId}`, {
        method: 'DELETE',
      });

      if (!response.ok) throw new Error('Error borrando workflow');

      setError(null);
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setCargando(false);
    }
  }, []);

  return {
    cargando,
    error,
    crearWorkflow,
    obtenerWorkflows,
    obtenerWorkflow,
    actualizarWorkflow,
    ejecutarWorkflow,
    obtenerEjecuciones,
    obtenerEjecucion,
    descargarResultado,
    borrarWorkflow,
  };
};

export default useWorkflowAPI;
