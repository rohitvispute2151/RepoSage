import { defineConfig, devices } from '@playwright/test'

/** Runs the UI against the real docker-compose stack (API on :8000). Requires the stack to be up and healthy. */
export default defineConfig({
  testDir: 'e2e/stack',
  workers: 1,
  reporter: [['list']],
  use: { baseURL: 'http://127.0.0.1:5174', trace: 'retain-on-failure' },
  projects: [{ name: 'stack', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'bunx vite --host 127.0.0.1 --port 5174 --strictPort',
    url: 'http://127.0.0.1:5174',
    reuseExistingServer: !process.env.CI,
    env: { API_PROXY: process.env.API_PROXY ?? 'http://127.0.0.1:8000' },
  },
})
