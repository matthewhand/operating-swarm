import { test, expect } from '@playwright/test'

/**
 * REQ-72 / #417 — merged chrome gaps on current main.
 * Covers shipped Grok rail / Search / remotes stub / roles / settings.
 * Does not cover in-flight PRs (344, 370, 383, 400, 403, …).
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
    {
      id: 'stewie',
      object: 'blueprint',
      name: 'Stewie',
      description: 'Helpful agent',
      abbreviation: null,
      required_mcp_servers: [],
      tags: [],
      installed: true,
      compiled: true,
      rail: true,
    },
    {
      id: 'cos',
      object: 'blueprint',
      name: 'Pat',
      description: 'Talks to any team.',
      abbreviation: 'CoS',
      role: 'chief_of_staff',
      required_mcp_servers: [],
      tags: [],
      installed: true,
      compiled: true,
      rail: true,
    },
  ],
}

const ROSTERS = {
  object: 'list',
  data: [
    {
      id: 'office',
      object: 'team_roster',
      name: 'Office',
      members: [
        {
          id: 'research',
          kind: 'team',
          team_id: 'research',
          role: 'default',
          source: 'team:research',
        },
      ],
      wires: { handoff: true, as_tool: true },
    },
    {
      id: 'research',
      object: 'team_roster',
      name: 'Research',
      members: [{ id: 'ada', kind: 'api', role: 'default', source: 'blueprint:ada' }],
      wires: { handoff: true, as_tool: true },
    },
    {
      id: 'demo-team',
      object: 'team_roster',
      name: 'Demo Team',
      description: 'Example multi-agent roster',
      members: [{ id: 'codey', name: 'Codey', kind: 'agent', role: 'coder' }],
    },
  ],
}

const HERDR = {
  object: 'list',
  data: [
    {
      id: 1,
      object: 'herdr.agent',
      kind: 'herdr',
      name: 'w3:p1',
      remote: '',
      created_at: '2026-09-03T00:00:00Z',
      updated_at: '2026-09-03T00:00:00Z',
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
  await page.route('**/team_rosters.json', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(ROSTERS),
    })
  })
  await page.route('**/v1/team-rosters**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(ROSTERS),
    })
  })
  await page.route('**/v1/herdr-agents**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(HERDR),
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
      body: JSON.stringify({ object: 'list', data: [] }),
    })
  })
  await page.route('**/chat/thread/**', async (route) => {
    const url = new URL(route.request().url())
    const agent = url.searchParams.get('agent') || 'support'
    const letter = agent === 'stewie' ? 'B' : agent === 'codey' ? 'A' : 'S'
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        agent_id: agent,
        conversation_id: `agt-${agent}`,
        messages: [
          { role: 'user', content: `prior question ${letter}` },
          { role: 'assistant', content: `prior answer ${letter}` },
        ],
        summaries: [],
      }),
    })
  })
  return remotesHits
}

test('REQ-14 #319: rail agent switch rehydrates distinct persisted threads', async ({ page }) => {
  await stubChromeApis(page)
  await page.goto('/chat?blueprint=codey')
  await expect(page.getByText('prior question A')).toBeVisible()
  await expect(page.getByText('prior question B')).toHaveCount(0)

  await page.getByRole('navigation', { name: 'Agent list' }).getByRole('link', { name: /Stewie/ }).click()
  await expect(page).toHaveURL(/blueprint=stewie/)
  await expect(page.getByText('prior question B')).toBeVisible()
  await expect(page.getByText('prior question A')).toHaveCount(0)

  await page.getByRole('navigation', { name: 'Agent list' }).getByRole('link', { name: /Codey/ }).click()
  await expect(page).toHaveURL(/blueprint=codey/)
  await expect(page.getByText('prior question A')).toBeVisible()
})

test('REQ-5c #322: Search palette choosing a bot navigates to that chat', async ({ page }) => {
  await stubChromeApis(page)
  await page.goto('/chat')
  await page.getByRole('button', { name: 'Search' }).click()
  const palette = page.getByRole('dialog', { name: 'Search' })
  await expect(palette).toBeVisible()
  await palette.getByRole('option', { name: /Codey/ }).click()
  await expect(page).toHaveURL(/\/chat\/?\?blueprint=codey/)
  await expect(palette).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Codey' })).toBeVisible()
})

test('REQ-54: mobile header opens the tucked rail and closes after an agent pick', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await stubChromeApis(page)
  await page.goto('/')
  const open = page.getByRole('button', { name: 'Open agent list' })
  await expect(open).toBeVisible()
  const backdrop = page.locator('button.fixed.inset-0[aria-label="Close agents sidebar"]')
  await expect(backdrop).toBeHidden()

  await open.click()
  await expect(backdrop).toBeVisible()
  const rail = page.getByRole('navigation', { name: 'Agent list' })
  await expect(rail.getByRole('link', { name: /Codey/ })).toBeVisible()
  await rail.getByRole('link', { name: /Codey/ }).click()
  await expect(page).toHaveURL(/blueprint=codey/)
  await expect(backdrop).toBeHidden()
})

test('REQ-5c #322: pin persists across reload; Unpin clears the grid', async ({ page }) => {
  await stubChromeApis(page)
  await page.goto('/chat')
  const list = page.getByRole('navigation', { name: 'Agent list' })
  const codey = list.getByRole('link', { name: /Codey/ })
  await codey.click({ button: 'right' })
  await page.getByRole('menuitem', { name: /^Pin$/i }).click()
  const grid = page.getByLabel('Pinned agents')
  await expect(grid.getByRole('link', { name: 'Codey' })).toBeVisible()
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('swarm_pinned_agents')))
    .toContain('codey')

  await page.reload()
  await expect(page.getByLabel('Pinned agents').getByRole('link', { name: 'Codey' })).toBeVisible()
  await expect(list.getByRole('link', { name: /Codey/ })).toHaveCount(0)

  await page.getByLabel('Pinned agents').getByRole('link', { name: 'Codey' }).click({ button: 'right' })
  await page.getByRole('menuitem', { name: /^Unpin$/i }).click()
  await expect(page.getByLabel('Pinned agents').getByRole('link', { name: 'Codey' })).toHaveCount(0)
  await expect(list.getByRole('link', { name: /Codey/ })).toBeVisible()
})

test('REQ-28 #345: CoS badge and nested team rows render in the rail', async ({ page }) => {
  await stubChromeApis(page)
  await page.goto('/chat')
  const list = page.getByRole('navigation', { name: 'Agent list' })
  const cos = list.getByRole('link', { name: /Pat/ })
  await expect(cos).toBeVisible()
  await expect(cos).toHaveAttribute('data-role', 'chief_of_staff')
  await expect(cos.getByText('CoS')).toBeVisible()

  const office = list.getByRole('link', { name: /Office/ })
  await expect(office).toHaveAttribute('data-kind', 'team')
  const research = list.getByRole('link', { name: /Research/ })
  await expect(research).toHaveAttribute('data-kind', 'team')
  await expect(research.locator('xpath=ancestor::ul[contains(@class,"os-agent-team-nest")]')).toHaveCount(1)
})

test('REQ-21 #332: Herdr rail row links to Teams#herdr-members', async ({ page }) => {
  await stubChromeApis(page)
  await page.goto('/chat')
  const herdr = page.getByRole('navigation', { name: 'Agent list' }).getByRole('link', { name: /w3:p1/ })
  await expect(herdr).toBeVisible()
  await expect(herdr).toHaveAttribute('href', '/teams/#herdr-members')
  await expect(herdr).toContainText('Herdr · localhost')
})

test('REQ-24 #342: dragging a team row onto Hidden stores team:<id>', async ({ page }) => {
  await stubChromeApis(page)
  await page.goto('/chat')
  const list = page.getByRole('navigation', { name: 'Agent list' })
  const team = list.getByRole('link', { name: /Demo Team \(team\)/ })
  await expect(team).toBeVisible()
  const zone = page.getByRole('region', { name: 'Hidden Bots' })
  await team.evaluate((el) => {
    el.dispatchEvent(
      new DragEvent('dragstart', { bubbles: true, cancelable: true, dataTransfer: new DataTransfer() }),
    )
  })
  await zone.evaluate((el) => {
    const dt = new DataTransfer()
    el.dispatchEvent(new DragEvent('dragenter', { bubbles: true, cancelable: true, dataTransfer: dt }))
    el.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: dt }))
    el.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }))
  })
  await expect(list.getByRole('link', { name: /Demo Team \(team\)/ })).toHaveCount(0)
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('swarm_hidden_agents')))
    .toContain('team:demo-team')
})

test('REQ-5c #322 / #805: / canonicalizes onto Support; Plugins popup searches tools', async ({ page }) => {
  await stubChromeApis(page)
  await page.goto('/')
  await expect(page).toHaveURL(/blueprint=support/)
  await expect(page.getByRole('heading', { name: 'Support' })).toBeVisible()

  await page.getByRole('button', { name: /Plugins/i }).click()
  const plugins = page.getByRole('dialog', { name: 'Plugins' })
  await expect(plugins).toBeVisible()
  await expect(plugins.getByRole('combobox', { name: 'Filter tools' })).toBeVisible()
  await expect(plugins.getByRole('switch', { name: /Web Search Off/i })).toBeVisible()
  await plugins.getByRole('button', { name: 'Close plugins' }).click()
  await expect(plugins).toHaveCount(0)
})

test('REQ-59: settings remotes start empty with Add remote (no default kind cards)', async ({
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
  await expect(sheet.getByRole('button', { name: 'Rakazo' })).toHaveCount(0)
  await expect(sheet.getByText(/placeholder remote/i)).toHaveCount(0)
  await expect(sheet.getByText(/\bOMB\b/)).toHaveCount(0)
})
