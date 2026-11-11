import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// The backend binds 127.0.0.1 only; "localhost" can resolve to ::1 and miss it.
const api = `127.0.0.1:${process.env.JULI_API_PORT || 8000}`

export default defineConfig({
  // Absolute URLs such as /mascot/... are files in public/, served as they are:
  // don't turn them into imports (Vitest 4 can't load those as modules).
  plugins: [vue({ template: { transformAssetUrls: { includeAbsolute: false } } })],
  server: {
    port: 3000,
    strictPort: true,
    proxy: {
      '/api': { target: `http://${api}` },
      '/ws': { target: `ws://${api}`, ws: true },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.js'],
    include: ['tests/**/*.test.js'],
    coverage: { provider: 'v8', include: ['src/**'], reporter: ['text', 'text-summary'] },
  },
})
