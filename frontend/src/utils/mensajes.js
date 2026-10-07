// Mensajes de error para el usuario (spec 001, H4 y CA5). Antes cada pantalla
// enseñaba lo que tuviera a mano: `e.message` del navegador ("Failed to
// fetch", "Unexpected token < in JSON"), el `detail` del servidor tal cual,
// con rutas incluidas, o un alert() que bloqueaba la página. Aquí se decide
// una vez qué se puede enseñar y con qué forma: "No se pudo <acción>: <motivo>."

// Un error cuyo texto ya está pensado para el usuario: lo ha escrito el
// servidor en `detail` (ya limpio) o el propio frontend. Cualquier otro error
// (red, JSON roto, fallo de programación) se enseña sin su texto.
export class ErrorLegible extends Error {}

// Rutas del servidor o del equipo (/app/uploads/x.sdf, C:\algo\y.py,
// algoritmos/z.py): se deja solo el nombre del fichero, que es lo que el
// usuario reconoce. Las relativas solo si acaban en un fichero con extension,
// para no partir textos como "y/o" o "3/5".
const RUTA_ABSOLUTA = /(?:[A-Za-z]:)?(?:[\\/][^\s\\/:'"()]+)+[\\/]([^\s\\/:'"()]+)/g;
const RUTA_RELATIVA = /(?:[^\s\\/:'"()]+[\\/])+([^\s\\/:'"()]+\.[A-Za-z0-9]{1,5})\b/g;
// Los dos directorios de la plataforma se quitan siempre, aunque el nombre que
// sigue lleve espacios ("algoritmos/Docking con Smina.py").
const DIRECTORIO_SERVIDOR = /\b(?:algoritmos|uploads)[\\/]/g;

// `detail` de FastAPI → texto, o null si no hay nada que se pueda enseñar.
// Los errores de validación (422) llegan como lista de {msg}.
export function textoDetalle(detail) {
  if (Array.isArray(detail)) detail = detail.map(e => e?.msg).filter(Boolean).join('; ');
  if (typeof detail !== 'string' || !detail.trim()) return null;
  // Una traza de Python no le dice nada a quien la lee: mejor el mensaje
  // generico que un muro de "File ..., line ...".
  if (/Traceback|File "|line \d+, in /.test(detail)) return null;
  return detail
    .replace(RUTA_ABSOLUTA, '$1')
    .replace(RUTA_RELATIVA, '$1')
    .replace(DIRECTORIO_SERVIDOR, '')
    .trim();
}

// El error que corresponde a una respuesta que no es ok, para lanzarlo:
//   if (!resp.ok) throw await errorDeRespuesta(resp);
export async function errorDeRespuesta(resp) {
  const datos = await resp.json().catch(() => ({}));
  const texto = textoDetalle(datos.detail);
  const error = texto ? new ErrorLegible(texto) : new Error(`HTTP ${resp.status}`);
  // El código, para quien tenga que distinguir casos (p. ej. el visor 3D:
  // un 404 es que el fichero ya no está y hay que quitarlo del hueco).
  error.status = resp.status;
  return error;
}

// "No se pudo <accion>: <motivo>." si se sabe un motivo enseñable, y si no,
// que se reintente. `motivo` puede ser un error o ya un texto.
export function mensajeError(accion, motivo) {
  const texto = motivo instanceof ErrorLegible ? motivo.message
    : typeof motivo === 'string' ? motivo
    : null;
  if (!texto) {
    return `No se pudo ${accion}. Inténtalo de nuevo y, si vuelve a fallar, avisa al administrador.`;
  }
  return `No se pudo ${accion}: ${texto.replace(/[.\s]+$/, '')}.`;
}
