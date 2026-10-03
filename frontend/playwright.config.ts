import { defineConfig } from '@playwright/test'
import path from 'node:path'

export default defineConfig({
  testDir: './tests',
  outputDir: process.env.VIDEO_NOTES_E2E_OUTPUT_DIR || 'test-results',
  workers: 1,
  retries: 0,
  timeout: 60000,
  expect: { timeout: 15000 },
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:3422',
    browserName: 'chromium',
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: `uv run --no-sync uvicorn app.main:app --app-dir "${process.env.VIDEO_NOTES_BACKEND_APP_DIR || path.resolve(__dirname, '../backend')}" --host 127.0.0.1 --port 8422`,
      cwd: '../backend',
      url: 'http://127.0.0.1:8422/api/health',
      reuseExistingServer: false,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 2000 },
    },
    {
      command: 'pnpm start',
      url: 'http://127.0.0.1:3422',
      reuseExistingServer: false,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 2000 },
    },
  ],
})
