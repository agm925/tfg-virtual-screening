import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],

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
})
