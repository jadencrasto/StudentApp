import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000' },
      '/auth/google': { target: 'http://127.0.0.1:8000' },
      '/events': { target: 'http://127.0.0.1:8000' },
      '/colleges': { target: 'http://127.0.0.1:8000' },
      '/extract': { target: 'http://127.0.0.1:8000' },
      '/health': { target: 'http://127.0.0.1:8000' },
    }
  }
})
