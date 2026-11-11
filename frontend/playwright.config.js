// End-to-end tests: the built dashboard and the real API, with a fake
// OpenAI-compatible model server, driven in Chromium. Run `npm run build`
// first, then `npm run e2e`.
import { defineConfig } from '@playwright/test'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

const PORT = 8040
const LLM_PORT = 8099
// Each run gets an empty data folder, so no state leaks between runs.
process.env.JULI_E2E_DATA ||= mkdtempSync(join(tmpdir(), 'juli-e2e-'))
const python = process.env.JULI_PYTHON || (process.platform === 'win32' ? `"${resolve('../.venv/Scripts/python.exe')}"` : 'python')

export default defineConfig({
  testDir: 'e2e',
  workers: 1, // one server, one crew: the tests share it in order
  timeout: 120_000,
  reporter: process.env.CI ? [['list'], ['github']] : 'list',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    viewport: { width: 1440, height: 900 },
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: `${python} e2e/fake_llm.py ${LLM_PORT}`,
      url: `http://127.0.0.1:${LLM_PORT}/v1/models`,
      reuseExistingServer: false,
      timeout: 180_000, // a cold Python start with every SDK can be slow on a busy machine
    },
    {
      command: `${python} e2e/serve.py ${PORT}`,
      url: `http://127.0.0.1:${PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 180_000, // a cold Python start with every SDK can be slow on a busy machine
      env: { ...process.env, JULI_TOKEN: 'e2e-session', JULI_DATA_DIR: process.env.JULI_E2E_DATA },
    },
  ],
})
