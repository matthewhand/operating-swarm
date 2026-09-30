/**
 * #1230 — Compact is API-only and never renders a "not available" state.
 *
 * Browser-level guard for the user report: a CLI seat's composer `+` menu
 * must list NO Compact control (and no disabled/"not available" copy). An API
 * seat keeps the live action. Runs against the production build via the
 * Playwright webServer (hermetic: every /v1 call and the chat socket mocked).
 */
import { test, expect } from '@playwright/test'

const BLUEPRINTS = {
  object: 'list',
  data: [
    {
      id: 'codey',
      object: 'blueprint',
      name: 'Codey',
      description: 'Code assistant',
      abbreviation: null,
      required_mcp_servers: [],
      tags: [],
      installed: true,
      compiled: true,
      rail: true,
    },
    {
      id: 'cli_agent',
      object: 'blueprint',
      name: 'CLI Agent',
      description: 'Single CLI',
      abbreviation: null,
      required_mcp_servers: [],
      tags: ['cli'],
      installed: true,
      compiled: true,
      rail: true,
    },
  ],
}

const CLI_AGENTS = {
  clis: ['grok'],
  known: ['grok'],
  configured: ['grok'],
  discovered: ['grok'],
  installed: ['grok'],
  default_cli: 'grok',
  native_consensus: {},
  catalog: {},
  rail: [
    {
      id: 'cli_grok',
      object: 'cli.agent',
      name: 'grok',
      cli: 'grok',
      kind: 'cli',
      description: 'grok CLI',
      installed: true,
    },
  ],
  slash_commands: {},
  cli_compact: {},
  // #551: published kind-base declarations — CLI compact OFF.
  seat_capabilities: {
    cli: {
      attach: { enabled: false, reason: 'CLI attachments off' },
      compact: { enabled: false, reason: 'Compact is API-only' },
      plugins: { enabled: false, reason: 'API/blueprint only' },
      routines: { enabled: false, reason: 'swarm-side only' },
    },
  },
}

async function stubChatApis(page: import('@playwright/test').Page) {
  await page.route('**/v1/blueprints**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(BLUEPRINTS),
    })
  })
  await page.route('**/v1/cli-agents**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(CLI_AGENTS),
    })
  })
  await page.route('**/v1/llm-profiles**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ default_llm_ready: true }),
    })
  })
  await page.route('**/health**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok' }),
    })
  })
  // In-page socket mock: open immediately, no frames needed for menu checks.
  await page.addInitScript(() => {
    class SilentWebSocket {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3
      readyState = 1
      url: string
      onopen: ((ev: Event) => void) | null = null
      onmessage: ((ev: MessageEvent) => void) | null = null
      onclose: ((ev: CloseEvent) => void) | null = null
      onerror: ((ev: Event) => void) | null = null
      constructor(url: string) {
        this.url = url
        queueMicrotask(() => this.onopen?.(new Event('open')))
      }
      send() {}
      close() {
        this.readyState = 3
      }
    }
    window.WebSocket = SilentWebSocket as unknown as typeof WebSocket
  })
}

test('#1230: a CLI seat offers NO Compact and no "not available" copy', async ({
  page,
}) => {
  await stubChatApis(page)
  await page.goto('/chat?blueprint=cli_agent&mode=cli&cli=grok')

  const plus = page.getByTestId('composer-plus-button')
  await expect(plus).toBeVisible()
  await plus.click()

  // The menu is open — Add files is there …
  await expect(page.getByRole('menuitem', { name: 'Add files' })).toBeVisible()
  // … but Compact is absent, never disabled / "not available".
  await expect(page.getByTestId('composer-compact-button')).toHaveCount(0)
  await expect(page.getByRole('menuitem', { name: 'Compact' })).toHaveCount(0)
  await expect(page.getByText(/compact not available/i)).toHaveCount(0)
  await expect(page.getByText(/no api is configured/i)).toHaveCount(0)
})

test('#1230: an API seat keeps the live Compact action', async ({ page }) => {
  await stubChatApis(page)
  await page.goto('/chat?blueprint=codey')

  const plus = page.getByTestId('composer-plus-button')
  await expect(plus).toBeVisible()
  await plus.click()

  const compact = page.getByRole('menuitem', { name: 'Compact' })
  await expect(compact).toBeVisible()
  await expect(compact).not.toHaveAttribute('aria-disabled', 'true')
})
