// Utilidades que comparten Inicio y Resultados para enseñar ejecuciones y
// sus ficheros.

// Los ficheros de un cribado llevan en el nombre la base de datos, la ejecución
// y la fecha, para que dos ejecuciones no se pisen. Como texto de un botón es
// ilegible: se enseña qué es, y el nombre completo queda en el tooltip.
const ETIQUETA_FICHERO = {
  moleculas_:   'Moléculas',
  propiedades_: 'Propiedades',
  ranking_:     'Ranking',
  poses_:       'Poses',
  resultados_:  'Resultados completos',
};

export function etiquetaFichero(nombre) {
  const prefijo = Object.keys(ETIQUETA_FICHERO).find(p => nombre.startsWith(p));
  return prefijo ? `${ETIQUETA_FICHERO[prefijo]} (${nombre.split('.').pop().toUpperCase()})` : nombre;
}

export function formatFecha(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' })
    + ' ' + d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
}

// Las peticiones guardan el estado en mayúsculas y las ejecuciones de
// workflow en minúsculas: se normaliza aquí para que las dos tablas hablen
// igual.
const ESTADOS = {
  pendiente:  'En cola',
  procesando: 'Procesando',
  completado: 'Completado',
  error:      'Error',
  cancelado:  'Cancelado',
};

export function claseEstado(estado) {
  const clave = (estado || '').toLowerCase();
  return ESTADOS[clave] ? clave : 'pendiente';
}

export function textoEstado(estado) {
  return ESTADOS[(estado || '').toLowerCase()] || estado;
}

export const ESTADOS_ACTIVOS = ['pendiente', 'procesando'];

export function estaActivo(estado) {
  return ESTADOS_ACTIVOS.includes((estado || '').toLowerCase());
}
