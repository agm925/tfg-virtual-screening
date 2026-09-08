// Cliente API centralizado.
//
// Antes, cada componente hacía fetch(`http://localhost:8000/...`) por su
// cuenta y mandaba usuario_id a mano en cada petición. Desde que el backend
// exige JWT (ver app/auth.py), toda petición a un endpoint protegido tiene
// que llevar la cabecera Authorization: Bearer <token> — centralizarlo aquí
// evita repetir esa lógica (y el manejo de expiración/401) en 13 sitios.

// Ruta relativa, no URL absoluta: la API se sirve bajo el mismo origen que la
// SPA, vía el proxy de nginx en producción (frontend/nginx.conf) o el de Vite
// en desarrollo (frontend/vite.config.js). Antes esto era
// 'http://localhost:8000', lo que ataba la aplicación a esa máquina: abierta
// desde la IP de red de otro equipo, el login fallaba y los desplegables de
// algoritmos salían vacíos. VITE_API_BASE permite apuntar a un backend en otro
// origen si algún despliegue lo necesita.
export const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

const TOKEN_KEY = 'access_token';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

// Decodifica el payload del JWT (sin verificar la firma — eso solo puede
// hacerlo el backend, que es quien tiene la clave secreta) para poder
// comprobar la expiración en el cliente y no esperar a un 401 para avisar.
export function payloadToken(token) {
  try {
    return JSON.parse(atob(token.split('.')[1]));
  } catch {
    return null;
  }
}

export function tokenValido(token) {
  if (!token) return false;
  const payload = payloadToken(token);
  if (!payload?.exp) return false;
  return payload.exp * 1000 > Date.now();
}

// Se registra desde App.jsx al montar; permite que un 401 fuerce el logout
// y la vuelta a la pantalla de login desde cualquier punto de la app.
let alExpirar = null;
export function alExpirarSesion(callback) {
  alExpirar = callback;
}

function authHeaders(headers = {}) {
  const token = getToken();
  return token ? { ...headers, Authorization: `Bearer ${token}` } : headers;
}

// Envoltorio de fetch: añade la cabecera Authorization si hay sesión, y
// fuerza logout si el backend responde 401 (token ausente, caducado o
// inválido) en vez de dejar que cada componente lo gestione por separado.
export async function apiFetch(ruta, opciones = {}) {
  const resp = await fetch(`${API_BASE}${ruta}`, {
    ...opciones,
    headers: authHeaders(opciones.headers),
  });
  if (resp.status === 401 && alExpirar) {
    alExpirar();
  }
  return resp;
}

// Para descargas: /descargar/{id} exige el token, y un <a href> normal no
// puede mandar cabeceras. Se descarga el fichero como blob autenticado y se
// dispara la descarga en el navegador mediante un enlace temporal.
export async function descargarConToken(ruta, nombreSugerido) {
  const resp = await apiFetch(ruta);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || 'No se pudo descargar el archivo');
  }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = nombreSugerido || 'descarga';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
