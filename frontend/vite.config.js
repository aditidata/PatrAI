import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/health': 'http://localhost:8000',
      '/bookings': 'http://localhost:8000',
      '/preferences': 'http://localhost:8000',
      '/process': 'http://localhost:8000',
      '/webhook': 'http://localhost:8000',
      '/negotiation': 'http://localhost:8000',
    },
  },
  build: { outDir: 'dist' },
})
