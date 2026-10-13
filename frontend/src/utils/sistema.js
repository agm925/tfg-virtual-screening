// Textos de la página Sistema (spec 009). El estado de las copias lo decide
// el backend (app/copias_estado.py); aquí solo se dice en lenguaje llano y
// sin el error técnico, que queda en el log del servidor (principio 7).

const AVISOS_COPIAS = {
  sin_copias: 'Todavía no se ha hecho ninguna copia de seguridad. Revisa que el servicio de copias esté en marcha.',
  atrasada: 'Hace más de un día que no se hace una copia de seguridad. Revisa que el servicio de copias esté en marcha.',
  fallida: 'La última copia de seguridad ha fallado. Los detalles están en el registro del servicio de copias.',
};

// null si todo va bien; si no, el aviso. Un estado que no se conoce también
// avisa: mejor un aviso de más que callar un problema con las copias.
export function avisoCopias(copias) {
  if (copias?.estado === 'ok') return null;
  return AVISOS_COPIAS[copias?.estado] ?? 'No se puede saber cómo están las copias de seguridad.';
}

export function tamanoLegible(bytes) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1).replace('.', ',')} GB`;
  if (bytes >= 1024 ** 2) return `${Math.round(bytes / 1024 ** 2)} MB`;
  return `${Math.round(bytes / 1024)} KB`;
}
