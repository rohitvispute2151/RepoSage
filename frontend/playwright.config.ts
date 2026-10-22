import { defineConfig, devices } from '@playwright/test'

const WEB = 5173
const MOCK = 8788

export default defineConfig({
  testDir: 'e2e/mock',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: { baseURL: `http://127.0.0.1:${WEB}`, trace: 'retain-on-failure' },
  projects: [{ name: 'mock', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    { command: 'bun run mock/server.ts', url: `http://127.0.0.1:${MOCK}/healthz`, reuseExistingServer: !process.env.CI, env: { MOCK_PORT: String(MOCK), MOCK_STEP_MS: '60' } },
    { command: `bunx vite --host 127.0.0.1 --port ${WEB} --strictPort`, url: `http://127.0.0.1:${WEB}`, reuseExistingServer: !process.env.CI, env: { API_PROXY: `http://127.0.0.1:${MOCK}` } },
  ],
})
