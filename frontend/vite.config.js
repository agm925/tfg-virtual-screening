import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// Explícito: el linter trata este fichero como código de navegador, sin `process`.
import process from 'node:process'

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [react()],

  // Dirección bajo la que se sirve la aplicación (spec 004). En el servidor
  // RTX cuelga de https://rt.hpca.ual.es/molserver, no de la raíz, así que el
  // build pide sus ficheros a /molserver/assets/... En desarrollo sigue en /,
  // como siempre. VITE_BASE la cambia al compilar (por ejemplo, VITE_BASE=/).
  base: process.env.VITE_BASE || (command === 'build' ? '/molserver/' : '/'),

  // En producción es nginx quien sirve la SPA y reenvía /api/ al backend
  // (ver frontend/nginx.conf). En desarrollo no hay nginx, así que el servidor
  // de Vite hace de proxy con exactamente el mismo prefijo: así el frontend usa
  // siempre rutas relativas /api/... y se comporta igual en los dos entornos,
  // sin URLs absolutas hardcodeadas ni peticiones cross-origin.
  server: {
    proxy: {
      '/api': {
        target: process.env.VITE_BACKEND_ORIGIN || 'http://localhost:8000',
        changeOrigin: true,
        // Igual que la barra final de proxy_pass en nginx: quita el prefijo
        // /api antes de reenviar, porque FastAPI declara las rutas sin él.
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
}))
