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
  clis: ['claude', 'codex', 'gemini', 'grok', 'opencode'],
  discovered: ['grok'],
  installed: ['grok'],
  configured: ['grok'],
  native_consensus: {},
  catalog: {},
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
}

test('CLI-agent chat lists discovered CLIs and Manage CLI, not blueprints', async ({
  page,
}) => {
  await stubChatApis(page)
  await page.goto('/chat?blueprint=cli_agent')

  const picker = page.getByTestId('navbar-routing-picker')
  await expect(picker).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Blueprint' })).toHaveCount(0)
  await page.getByTestId('routing-pill-agent').click()
  const menu = page.getByTestId('routing-menu-agent')
  await expect(menu.getByRole('menuitem', { name: 'grok' })).toBeVisible()
  await expect(menu.getByRole('menuitem', { name: 'Manage CLI' })).toBeVisible()
  await expect(menu.getByRole('menuitem', { name: 'Codey' })).toHaveCount(0)
})

test('blueprint-mode chat keeps Grok-Bot chrome without a Blueprint dropdown', async ({
  page,
}) => {
  await stubChatApis(page)
  await page.goto('/chat?blueprint=codey')

  await expect(page.getByRole('heading', { name: 'Codey' })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Blueprint' })).toHaveCount(0)
  await expect(page.getByRole('combobox', { name: 'CLI' })).toHaveCount(0)
  await expect(page.getByTestId('navbar-routing-picker')).toHaveCount(0)
  await expect(page.getByRole('menuitem', { name: /Manage CLI/i })).toHaveCount(0)
})

test('running PATH/config CLI outside the catalog is listed and selected', async ({
  page,
}) => {
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
      body: JSON.stringify({
        ...CLI_AGENTS,
        installed: ['antigravity'],
        configured: ['antigravity'],
        default_cli: 'antigravity',
      }),
    })
  })
  await page.goto('/chat?blueprint=cli_agent&cli=antigravity')

  const pill = page.getByTestId('routing-pill-agent')
  await expect(pill).toBeVisible()
  await expect(pill).toHaveAttribute('data-value', 'antigravity')
  await pill.click()
  await expect(page.getByRole('menuitem', { name: 'antigravity' })).toHaveCount(1)
  await expect(page.getByRole('menuitem', { name: 'Codey' })).toHaveCount(0)
})
