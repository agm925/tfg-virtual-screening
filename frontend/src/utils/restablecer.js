// El enlace del correo de «¿Has olvidado tu contraseña?» (spec 011) es
// {PUBLIC_URL}/#restablecer=<token>. Va en el fragmento y no en la consulta
// para que el token no llegue al servidor ni a sus registros de acceso.

// Solo los caracteres que produce secrets.token_urlsafe: cualquier otra cosa
// no es un enlace nuestro.
const PATRON = /^#restablecer=([A-Za-z0-9_-]+)$/;

export function tokenDeRestablecer(hash) {
  const encontrado = PATRON.exec(hash || '');
  return encontrado ? encontrado[1] : null;
}

// Lee el token y lo quita de la barra de direcciones, para que no quede en
// el historial ni a la vista de quien mire la pantalla. Se llama una sola vez
// al cargar la aplicación. `ventana` es `window`; se recibe para probarlo.
export function tomarTokenDeRestablecer(ventana = window) {
  const token = tokenDeRestablecer(ventana.location.hash);
  if (token) {
    ventana.history.replaceState(null, '', ventana.location.pathname + ventana.location.search);
  }
  return token;
}
