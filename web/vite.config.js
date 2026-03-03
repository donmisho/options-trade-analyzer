import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { readFileSync } from 'node:fs'

// Load self-signed certs for local HTTPS dev (required for Schwab OAuth).
// Falls back gracefully in CI/CD where certs don't exist.
function loadLocalHttps() {
  try {
    return {
      key: readFileSync('../key.pem'),
      cert: readFileSync('../cert.pem'),
    }
  } catch {
    return undefined
  }
}

export default defineConfig({
  plugins: [react()],
  server: {
    https: loadLocalHttps(),
    proxy: {
      '/api': {
        target: 'https://127.0.0.1:8000',
        secure: false,
        changeOrigin: true,
      },
    },
  },
})