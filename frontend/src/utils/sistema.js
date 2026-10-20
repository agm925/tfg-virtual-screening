// Textos de la página Sistema (spec 009). El estado de las copias lo decide
// el backend (app/copias_estado.py); aquí solo se dice en lenguaje llano y
// sin el error técnico, que queda en el log del servidor (principio 7). Los
// avisos son claves de los diccionarios (spec 014).
import { IDIOMA_POR_DEFECTO, traductor } from './idioma.js';

const AVISOS_COPIAS = {
  sin_copias: 'sistema.copias_sin',
  atrasada: 'sistema.copias_atrasada',
  fallida: 'sistema.copias_fallida',
};

// null si todo va bien; si no, el aviso. Un estado que no se conoce también
// avisa: mejor un aviso de más que callar un problema con las copias.
export function avisoCopias(copias, t = traductor(IDIOMA_POR_DEFECTO)) {
  if (copias?.estado === 'ok') return null;
  return t(AVISOS_COPIAS[copias?.estado] ?? 'sistema.copias_desconocido');
}

// La coma decimal solo en español: en inglés, 3.0 GB.
export function tamanoLegible(bytes, idioma = IDIOMA_POR_DEFECTO) {
  if (bytes >= 1024 ** 3) {
    const gb = (bytes / 1024 ** 3).toFixed(1);
    return `${idioma === 'es' ? gb.replace('.', ',') : gb} GB`;
  }
  if (bytes >= 1024 ** 2) return `${Math.round(bytes / 1024 ** 2)} MB`;
  return `${Math.round(bytes / 1024)} KB`;
}
