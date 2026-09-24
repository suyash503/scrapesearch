import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // In dev, Vite forwards /api/* to Django, so the browser only ever talks to one origin
    // (no CORS setup needed). In production nginx does the same job.
    // API_URL is set by docker-compose (http://api:8000). Running Vite on the host, it's 127.0.0.1.
    proxy: {
      '/api': process.env.API_URL ?? 'http://127.0.0.1:8000',
    },
  },
})
