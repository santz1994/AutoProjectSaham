import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true
  },
  server: {
    headers: {
      'Service-Worker-Allowed': '/',
      'Cache-Control': 'no-cache'
    },
    middlewareMode: false
  }
})
