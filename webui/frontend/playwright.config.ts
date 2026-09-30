import { defineConfig, devices } from '@playwright/test'

// E2E config for the Operating Swarm web UI.
//
// The SPA is served from the production build via `vite preview`, with the API
// (`/v1/*`, `/chat/*`) and websockets (`/ws/*`) proxied to the running dev stack
// on 127.0.0.1:8002 (see `VITE_PREVIEW_PROXY_TARGET` in vite.config.ts). That
// keeps the suite hermetic — no Django page render per navigation — while the
// same origin a browser uses for real traffic is reachable, unlike the previous
// empty-proxy preview that made every `/v1/*` and `/ws/*` call a dead port.
//
// Overrides:
//   VITE_PREVIEW_PROXY_TARGET  backend to proxy to (default http://127.0.0.1:8002)
//   PLAYWRIGHT_BASE_URL        skip the preview entirely and test this origin
//   PLAYWRIGHT_WORKERS         worker count
//   PLAYWRIGHT_SKIP_WEB_SERVER never start/adopt the preview server
const PREVIEW_PORT = 4173
const PREVIEW_URL = `http://127.0.0.1:${PREVIEW_PORT}`
const PROXY_TARGET =
  process.env.VITE_PREVIEW_PROXY_TARGET || 'http://127.0.0.1:8002'

const baseURL = process.env.PLAYWRIGHT_BASE_URL || PREVIEW_URL
const manageServer = !process.env.PLAYWRIGHT_SKIP_WEB_SERVER && !process.env.PLAYWRIGHT_BASE_URL

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  // The proxied dev stack shares one Postgres pool; cap the fan-out so a burst
  // of page loads cannot exhaust its connection slots. Override for a local
  // single-server run that does not touch the backend.
  workers: process.env.PLAYWRIGHT_WORKERS
    ? Number(process.env.PLAYWRIGHT_WORKERS)
    : 3,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: {
    baseURL,
    headless: true,
    launchOptions: { args: ['--no-sandbox', '--disable-gpu'] },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  // Build the SPA and serve it with the API/WS proxy. Reuse a preview that is
  // already up on the port; in CI always start fresh.
  webServer: manageServer
    ? {
        command: `npm run build && npm run serve -- --port ${PREVIEW_PORT} --strictPort`,
        url: PREVIEW_URL,
        // #1447 proof route is compiled out of production unless this is set.
        // The capture spec is the only consumer; deploy builds leave it unset.
        env: {
          VITE_PREVIEW_PROXY_TARGET: PROXY_TARGET,
          VITE_IA_1447_PROOF: '1',
        },
        timeout: 180_000,
        reuseExistingServer: !process.env.CI,
      }
    : undefined,
})
