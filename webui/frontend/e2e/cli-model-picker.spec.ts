/**
 * REQ-171C-3 / #103 / #870 — the CLI seat's model picker must list the CLI's OWN
 * probed models.
 *
 * The source of truth is `GET /v1/cli-agents/<cli>/models/` (fetchCliModels →
 * honestChatCliModels). The `list_models` argv table on `/v1/cli-agents/` is
 * just an argv to *run* a probe, never a model id list — a regression that
 * surfaced it as pickable rows would let an operator pin an unrunnable model.
 *
 * Deterministic: every API is routed in-page, no live CLI is invoked.
 */
import { test, expect } from '@playwright/test'

const CLI_INFO = {
  clis: ['grok'],
  known: ['grok'],
  installed: ['grok'],
  configured: ['grok'],
  discovered: ['grok'],
  default_cli: 'grok',
  // argv table — must never be rendered as model ids.
  list_models: { grok: ['grok', 'models'] },
  native_consensus: {},
  catalog: {},
}

const PROBED_MODELS = ['grok-live-alpha', 'grok-live-beta']

async function stubApis(page: import('@playwright/test').Page) {
  await page.route('**/v1/blueprints**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        object: 'list',
        data: [
          {
            id: 'cli_agent',
            object: 'blueprint',
            name: 'CLI agent',
            description: 'Single CLI',
            required_mcp_servers: [],
            tags: ['cli'],
            installed: true,
            compiled: true,
            rail: true,
          },
        ],
      }),
    }),
  )
  await page.route('**/v1/cli-agents**', (route) => {
    const url = route.request().url()
    if (url.includes('/models')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ cli: 'grok', models: PROBED_MODELS }),
      })
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(CLI_INFO),
    })
  })
  await page.route('**/v1/models**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'list', data: [] }),
    }),
  )
  await page.route('**/v1/teams**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'list', data: [] }),
    }),
  )
  await page.route('**/chat/thread**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        agent_id: 'cli_agent',
        conversation_id: 'cli-models-e2e',
        messages: [],
        summaries: [],
      }),
    }),
  )
  await page.route('**/health**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok' }),
    }),
  )
}

test('CLI model picker lists the CLI’s own probed models, not the argv table', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await stubApis(page)
  await page.goto('/chat?blueprint=cli_agent&mode=cli&cli=grok')

  const picker = page.getByTestId('navbar-routing-picker')
  await expect(picker).toBeVisible()

  // Two real probed models → the dialog descends into stage 2 rather than
  // auto-picking a lone row.
  await page.getByTestId('routing-pill-agent').click()
  const dialog = page.getByTestId('composer-picker')
  await expect(dialog).toBeVisible()
  await dialog.getByRole('option', { name: /grok/ }).first().click()

  // Stage 2 is fed by the probe response, not the argv table.
  await expect(dialog.getByRole('option', { name: PROBED_MODELS[0] })).toBeVisible()
  await expect(dialog.getByRole('option', { name: PROBED_MODELS[1] })).toBeVisible()
  // The legacy argv token is not a model id and must not be pickable.
  await expect(dialog.getByRole('option', { name: 'models', exact: true })).toHaveCount(0)

  await dialog.getByRole('option', { name: PROBED_MODELS[1] }).click()
  await expect(picker).toContainText(PROBED_MODELS[1])
  await expect(dialog).toHaveCount(0)
})
