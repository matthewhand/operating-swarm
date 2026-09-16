import { test, expect } from '@playwright/test'

/**
 * REQ-72 — shipped chrome overlays + remotes panes (#322 / #320 / #318 / #364).
 * Vite preview only. No live LAN, no :8001, no remotes health calls.
 */

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
  ],
}

const REMOTE_ROSTER = {
  object: 'list',
  data: [
    {
      id: 'harness-team',
      object: 'team_roster',
      name: 'Harness Team',
      description: 'Hermes / OpenMousBot / Rakazo as Team members (PR #318)',
      members: [
        { id: 'hermes', name: 'Hermes', kind: 'remote', role: 'default' },
        { id: 'omb', name: 'OpenMousBot', kind: 'remote', role: 'default' },
        { id: 'rakazo', name: 'Rakazo', kind: 'remote', role: 'default' },
      ],
    },
  ],
}

async function stubChromeApis(page: import('@playwright/test').Page) {
  const remotesHits: string[] = []
  await page.route('**/v1/blueprints**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(BLUEPRINTS),
    })
  })
  await page.route('**/v1/models**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'list', data: [] }),
    })
  })
  await page.route('**/v1/teams**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'list', data: [] }),
    })
  })
  await page.route('**/team_rosters.json', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(REMOTE_ROSTER),
    })
  })
  await page.route('**/v1/team-rosters**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(REMOTE_ROSTER),
    })
  })
  await page.route('**/v1/herdr-agents**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'list', data: [] }),
    })
  })
  await page.route('**/health**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok' }),
    })
  })
  await page.route('**/v1/remotes**', async (route) => {
    remotesHits.push(route.request().url())
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'list', kinds: [], configured: [], data: [] }),
    })
  })
  return remotesHits
}

test('settings / search / plugins overlays keep chat mounted (REQ-72 / #364 / #322 / #320)', async ({
  page,
}) => {
  const jsErrors: string[] = []
  page.on('pageerror', (e) => jsErrors.push(e.message))
  await stubChromeApis(page)
  await page.goto('/chat')

  const composer = page.getByRole('textbox', { name: 'Chat message' })
  await expect(composer).toBeVisible()
  await expect(page).toHaveURL(/\/chat\/?/)

  await page.getByRole('button', { name: 'Open settings' }).click()
  const settings = page.getByRole('dialog', { name: 'Settings' })
  await expect(settings).toBeVisible()
  await expect(settings).toHaveClass(/modal-end/)
  await expect(composer).toBeVisible()
  await expect(page).toHaveURL(/\/chat\/?/)
  await page.keyboard.press('Escape')
  await expect(settings).toBeHidden()
  await expect(composer).toBeVisible()

  await page.getByRole('button', { name: 'Search' }).click()
  const search = page.getByRole('dialog', { name: 'Search' })
  await expect(search).toBeVisible()
  await expect(composer).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Agent list' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(search).toHaveCount(0)
  await expect(composer).toBeVisible()

  await page.getByRole('button', { name: /Plugins/i }).click()
  const plugins = page.getByRole('dialog', { name: 'Plugins' })
  await expect(plugins).toBeVisible()
  await expect(plugins.getByRole('combobox', { name: 'Filter tools' })).toBeVisible()
  await expect(composer).toBeVisible()
  await expect(page).toHaveURL(/\/chat\/?/)

  expect(jsErrors, `uncaught JS errors: ${jsErrors.join(' | ')}`).toHaveLength(0)
})

test('settings remotes are opt-in; chat stays mounted (REQ-59 / REQ-48)', async ({
  page,
}) => {
  await stubChromeApis(page)
  await page.goto('/chat')
  await page.getByRole('button', { name: 'Open settings' }).click()
  const sheet = page.getByRole('dialog', { name: 'Settings' })
  await expect(sheet).toBeVisible()
  await sheet.getByRole('button', { name: 'Remotes' }).click()
  await expect(sheet.getByRole('button', { name: /Add remote/i })).toBeVisible()
  await expect(sheet.getByRole('button', { name: 'Hermes' })).toHaveCount(0)
  await expect(sheet.getByRole('button', { name: 'OMB' })).toHaveCount(0)
  await expect(sheet.getByText(/placeholder remote/i)).toHaveCount(0)
  await expect(page.getByRole('textbox', { name: 'Chat message' })).toBeVisible()
})

test('Search Bots tab lists agents; Actions stay operator links (REQ-17 / #322)', async ({
  page,
}) => {
  await stubChromeApis(page)
  await page.goto('/chat')
  await page.getByRole('button', { name: 'Search' }).click()
  const palette = page.getByRole('dialog', { name: 'Search' })
  await expect(palette).toBeVisible()

  await palette.getByRole('tab', { name: 'Bots' }).click()
  await expect(palette.getByRole('option', { name: /Support/ })).toBeVisible()
  await expect(palette.getByRole('option', { name: /Codey/ })).toBeVisible()
  await expect(page.getByRole('textbox', { name: 'Chat message' })).toBeVisible()

  await palette.getByRole('tab', { name: 'Actions' }).click()
  await expect(palette.getByRole('option', { name: /Toggle theme/ })).toBeVisible()
  await expect(palette.getByRole('option', { name: /Blueprints/ })).toBeVisible()
  await expect(palette.getByRole('option', { name: /Teams/ })).toBeVisible()
  // Several actions mention Settings (rail/system/MCP/CLI), so target the row.
  await expect(palette.locator('#os-search-row-action-settings')).toBeVisible()
})

test('team dropdown lists configured remotes as kind=remote members (PR #318 / REQ-23)', async ({
  page,
}) => {
  await stubChromeApis(page)
  await page.goto('/chat')
  const list = page.getByRole('navigation', { name: 'Agent list' })
  await list.getByRole('link', { name: /Harness Team \(team\)/ }).click()
  await expect(page).toHaveURL(/[?&]team=harness-team/)

  const dropdown = page.getByRole('combobox', { name: 'Team members' })
  await expect(dropdown).toBeVisible()
  await expect(dropdown.locator('option')).toHaveText([
    'All members',
    'Hermes (remote/default)',
    'OpenMousBot (remote/default)',
    'Rakazo (remote/default)',
    '──────────',
    'Manage Team',
  ])
  await expect(page.getByRole('textbox', { name: 'Chat message' })).toBeVisible()
})
