import { useState, useCallback } from 'react';
import { apiFetch, API_BASE, descargarConToken } from '../api/client';

const useWorkflowAPI = () => {
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState(null);

  // Crear workflow
  // (usuarioId ya no se envía: el backend toma el propietario del token JWT)
  const crearWorkflow = useCallback(async (workflow) => {
    setCargando(true);
    try {
      const formData = new FormData();
      formData.append('nombre', workflow.nombre);
      formData.append('descripcion', workflow.descripcion);

      const response = await apiFetch('/workflows', {
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
      const response = await apiFetch(`/workflows/usuario/${usuarioId}`);

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
      const response = await apiFetch(`/workflows/${workflowId}`);

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
      const response = await apiFetch(`/workflows/${workflowId}`, {
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

  // Ejecutar workflow — encola la tarea y devuelve { ejecucion_id }
  // (usuarioId ya no se envía: el backend toma el propietario del token JWT)
  const ejecutarWorkflow = useCallback(async (workflowId) => {
    setCargando(true);
    try {
      const response = await apiFetch(`/workflows/${workflowId}/ejecutar`, {
        method: 'POST',
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Error encolando workflow');
      }

      const data = await response.json();
      setError(null);
      return data; // { ejecucion_id, estado: 'pendiente', ... }
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setCargando(false);
    }
  }, []);

  // Polling: espera hasta que la ejecución termine (completado | error)
  // onProgreso recibe el objeto completo { estado, resultados_json: { progreso, total, molecula_actual, ... } }
  const esperarEjecucion = useCallback(async (ejecucionId, onProgreso) => {
    const INTERVALO = 3000; // 3 s
    return new Promise((resolve, reject) => {
      const tick = async () => {
        try {
          const resp = await apiFetch(`/workflows/ejecuciones/${ejecucionId}`);
          if (!resp.ok) { reject(new Error('Error consultando estado')); return; }
          const datos = await resp.json();
          if (onProgreso) onProgreso(datos);
          if (['completado', 'error', 'fallido', 'cancelado'].includes(datos.estado)) {
            resolve(datos.resultados_json || {});
          } else {
            setTimeout(tick, INTERVALO);
          }
        } catch (e) { reject(e); }
      };
      tick();
    });
  }, []);

  // Obtener ejecuciones de un workflow
  const obtenerEjecuciones = useCallback(async (workflowId) => {
    setCargando(true);
    try {
      const response = await apiFetch(`/workflows/${workflowId}/ejecuciones`);

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
      const response = await apiFetch(`/workflows/ejecuciones/${ejecucionId}`);

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

  // Descargar resultado (autenticado: /uploads/{nombre} es publico, pero se
  // centraliza aqui igualmente por si en el futuro deja de serlo)
  const descargarResultado = useCallback(async (nombreArchivo) => {
    try {
      await descargarConToken(`/uploads/${nombreArchivo}`, nombreArchivo);
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
      const response = await apiFetch(`/workflows/${workflowId}`, {
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
    esperarEjecucion,
    obtenerEjecuciones,
    obtenerEjecucion,
    descargarResultado,
    borrarWorkflow,
  };
};

export default useWorkflowAPI;
