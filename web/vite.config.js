import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { readFileSync } from 'node:fs'

export default defineConfig({
  plugins: [react()],
  server: {
    https: {
      key: readFileSync('../key.pem'),
      cert: readFileSync('../cert.pem'),
    },
    proxy: {
      '/api': {
        target: 'https://127.0.0.1:8000',
        secure: false,
        changeOrigin: true,
      },
    },
  },
})