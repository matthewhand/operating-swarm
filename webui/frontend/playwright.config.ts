import { defineConfig, devices } from '@playwright/test'

// E2E config for the Operating Swarm web UI. Serves the production build via
// `vite preview` on :4173 and runs headless Chromium. The cached browsers live
// under ~/.cache/ms-playwright (PLAYWRIGHT_BROWSERS_PATH default).
// Chat Send (REQ-13) uses e2e/helpers/mockInference.ts — no live LLM.
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:4173',
    headless: true,
    launchOptions: { args: ['--no-sandbox', '--disable-gpu'] },
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run build && npm run serve -- --port 4173 --strictPort',
    url: 'http://localhost:4173',
    timeout: 180_000,
    reuseExistingServer: !process.env.CI,
  },
})
