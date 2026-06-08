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
  // Vitest config (OTA-829). Shares the react plugin above so JSX transforms in
  // tests; `loadLocalHttps`/proxy only apply to the dev `server`, inert here.
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    css: false,
    // OneDrive-backed jsdom checkout is slow (see src/test/setup.js — async util
    // timeout already raised to 5s for the same reason). Under the full parallel
    // run, CPU saturation can push a test that stacks two 5s-budget async waits
    // past the 5s default test/hook timeout. Raise both so the suite is reliably
    // green; this is harness reliability only — no test logic depends on it.
    testTimeout: 15000,
    hookTimeout: 15000,
  },
})