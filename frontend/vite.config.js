import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite proxies /api to the Flask backend so the browser only ever talks to one
// origin. This keeps the JWT in an Authorization header and means there is no
// CORS preflight in the normal development flow (CORS is still enabled in the
// backend for direct access).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})