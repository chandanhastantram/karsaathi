import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const api = process.env.KARSAATHI_API || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  build: { chunkSizeWarningLimit: 900 }, // three.js lives in its own lazily loaded chunk
  server: {
    port: 5173,
    proxy: { '/api': api, '/portal': api, '/webhook': api },
  },
})
