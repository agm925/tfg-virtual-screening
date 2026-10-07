// Lo que MolServer guarda en el navegador (spec 004, R5): un único sitio para
// todas las claves de localStorage y sessionStorage.
//
// En el servidor la plataforma cuelga de https://rt.hpca.ual.es/molserver y
// comparte origen con las demás aplicaciones de rt.hpca.ual.es. El navegador
// separa el almacenamiento por origen, no por ruta: con claves genéricas como
// 'access_token', otra aplicación pisaría o borraría la sesión de MolServer, y
// el antiguo sessionStorage.clear() al cerrar sesión borraba también lo suyo.
// Por eso todas llevan un prefijo propio y al salir se borran solo esas.
//
// Sin React ni DOM: se prueba con node --test (tests/frontend/).

export const PREFIJO = 'molserver_';

// El JWT y el usuario de la sesión (localStorage: sobreviven a cerrar la pestaña).
export const CLAVE_TOKEN = `${PREFIJO}token`;
export const CLAVE_USUARIO = `${PREFIJO}usuario`;

// El estado del Constructor y del Visor 3D (sessionStorage: solo esta
// pestaña). Llevan el usuario para que otra cuenta en la misma pestaña no
// herede lo de la anterior.
export const claveEditor = (usuarioId) => `${PREFIJO}editor_${usuarioId}`;
export const claveVisor = (usuarioId) => `${PREFIJO}visor_${usuarioId}`;

export function esClaveDeMolServer(clave) {
  return typeof clave === 'string' && clave.startsWith(PREFIJO);
}

// Borra de cada almacén las claves de MolServer y nada más. Los almacenes se
// reciben como parámetro para poder probarlo sin navegador; si uno no está
// disponible (modo privado, datos del sitio bloqueados) se sigue con el resto.
export function olvidarSesion(almacenes = almacenesDelNavegador()) {
  for (const almacen of almacenes) {
    try {
      // Primero se recogen y luego se borran: borrar mientras se recorre
      // desplaza los índices y se saltaría claves.
      const propias = [];
      for (let i = 0; i < almacen.length; i += 1) {
        const clave = almacen.key(i);
        if (esClaveDeMolServer(clave)) propias.push(clave);
      }
      propias.forEach((clave) => almacen.removeItem(clave));
    } catch {
      /* sin acceso a este almacén: nada que borrar en él */
    }
  }
}

function almacenesDelNavegador() {
  const almacenes = [];
  try { almacenes.push(window.localStorage); } catch { /* bloqueado */ }
  try { almacenes.push(window.sessionStorage); } catch { /* bloqueado */ }
  return almacenes;
}
