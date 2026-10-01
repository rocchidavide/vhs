import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

const backend = process.env.VHS_BACKEND_URL ?? 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), vueDevTools()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // In docker-compose.dev.yml Vite listens on the Docker network (VHS_VITE_HOST=0.0.0.0) and
    // is reached only through Nginx: it publishes no port. Loopback when run by hand.
    host: process.env.VHS_VITE_HOST ?? '127.0.0.1',
    port: 5173,
    strictPort: true,
    // Same origin for SPA and API: session and CSRF cookies behave as they do behind Nginx.
    proxy: {
      '/api': backend,
      '/admin': backend,
      '/static': backend,
    },
  },
})
