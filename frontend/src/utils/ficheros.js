// Utilidades que comparten Inicio y Resultados para enseñar ejecuciones y
// sus ficheros. Los textos son claves de los diccionarios (spec 014); las
// funciones reciben el traductor `t` o el idioma, y sin él hablan en español.
import { IDIOMA_POR_DEFECTO, localeDe, traductor } from './idioma.js';

// Los ficheros de un cribado llevan en el nombre la base de datos, la ejecución
// y la fecha, para que dos ejecuciones no se pisen. Como texto de un botón es
// ilegible: se enseña qué es, y el nombre completo queda en el tooltip.
const ETIQUETA_FICHERO = {
  moleculas_:   'ficheros.moleculas',
  propiedades_: 'ficheros.propiedades',
  ranking_:     'ficheros.ranking',
  poses_:       'ficheros.poses',
  resultados_:  'ficheros.resultados',
};

export function etiquetaFichero(nombre, t = traductor(IDIOMA_POR_DEFECTO)) {
  const prefijo = Object.keys(ETIQUETA_FICHERO).find(p => nombre.startsWith(p));
  return prefijo ? `${t(ETIQUETA_FICHERO[prefijo])} (${nombre.split('.').pop().toUpperCase()})` : nombre;
}

export function formatFecha(iso, idioma = IDIOMA_POR_DEFECTO) {
  if (!iso) return '—';
  const d = new Date(iso);
  const locale = localeDe(idioma);
  return d.toLocaleDateString(locale, { day: '2-digit', month: '2-digit', year: 'numeric' })
    + ' ' + d.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
}

// Las peticiones guardan el estado en mayúsculas y las ejecuciones de
// workflow en minúsculas: se normaliza aquí para que las dos tablas hablen
// igual.
const ESTADOS = {
  pendiente:  'estado.pendiente',
  procesando: 'estado.procesando',
  completado: 'estado.completado',
  error:      'estado.error',
  cancelado:  'estado.cancelado',
};

export function claseEstado(estado) {
  const clave = (estado || '').toLowerCase();
  return ESTADOS[clave] ? clave : 'pendiente';
}

export function textoEstado(estado, t = traductor(IDIOMA_POR_DEFECTO)) {
  const clave = ESTADOS[(estado || '').toLowerCase()];
  return clave ? t(clave) : estado;
}

export const ESTADOS_ACTIVOS = ['pendiente', 'procesando'];

export function estaActivo(estado) {
  return ESTADOS_ACTIVOS.includes((estado || '').toLowerCase());
}

// El fichero que muestra el nodo «Elegir molécula» al cargarse (spec 012).
// Antes, si el guardado ya no estaba en la lista (borrado, o un resultado que
// se borró desde Resultados), se cambiaba en silencio por el primero: el
// workflow dejaba de ser el que se guardó, y en modo consulta se enseñaba un
// fichero que no era el que se usó. Ahora se mantiene y se marca (`falta`);
// solo un nodo nuevo, sin fichero, empieza con el primero.
export function seleccionInicial(guardado, lista) {
  if (guardado) return { nombre: guardado, falta: !lista.some(m => m.nombre === guardado) };
  return { nombre: lista[0]?.nombre ?? '', falta: false };
}
