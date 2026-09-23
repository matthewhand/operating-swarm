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
  ],
}

const ROSTERS = {
  object: 'list',
  data: [
    {
      id: 'demo-team',
      object: 'team_roster',
      name: 'Demo Team',
      description: 'Example multi-agent roster',
      members: [
        { id: 'codey', name: 'Codey', kind: 'agent', role: 'coder' },
        { id: 'stewie', name: 'Stewie', kind: 'agent', role: 'ops' },
      ],
    },
  ],
}

async function stubApis(page: import('@playwright/test').Page) {
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
  await page.route('**/v1/teams**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'list', data: [] }),
    })
  })
  await page.route('**/v1/remotes**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        object: 'list',
        kinds: [
          { id: 'hermes', label: 'Hermes' },
          { id: 'omb', label: 'OpenMousBot' },
          { id: 'rakazo', label: 'Rakazo' },
        ],
        configured: [],
        data: [],
      }),
    })
  })
}

test('sidepane mixes a team row; selecting it shows the unlabeled member dropdown', async ({
  page,
}) => {
  const jsErrors: string[] = []
  page.on('pageerror', (e) => jsErrors.push(e.message))
  await stubApis(page)
  await page.goto('/chat')

  const list = page.getByRole('navigation', { name: 'Agent list' })
  const team = list.getByRole('link', { name: /Demo Team \(team\)/ })
  await expect(team).toBeVisible()
  await expect(list.getByRole('link', { name: /Codey/ })).toBeVisible()

  // The team row opens the team chat directly now; per-session switching moved to
  // the row context menu ("Select session"), so there is no sessions dialog here.
  await team.click()
  await expect(page).toHaveURL(/[?&]team=demo-team/)

  const dropdown = page.getByRole('combobox', { name: 'Team members' })
  await expect(dropdown).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Blueprint' })).toHaveCount(0)
  // Remote chrome is gated to remote seats and remote-backed teams
  // (`showRemotesControl = isRemoteAgent || isRemoteBackedTeam`), so an
  // agent-only team renders neither the remote picker nor its empty state.
  await expect(page.getByRole('combobox', { name: 'Remote' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Add remote' })).toHaveCount(0)
  // Raw-text count is polluted by hidden nodes (closed sheets/selects), so limit
  // the check to what is actually on screen for a team seat.
  await expect(
    page.getByText('Blueprint', { exact: true }).locator('visible=true'),
  ).toHaveCount(0)
  await expect(dropdown.locator('option')).toHaveText([
    'All members',
    'Codey (agent/coder)',
    'Stewie (agent/ops)',
    '──────────',
    'Manage Team',
  ])
  // Opening a team resumes its default session, so the member dropdown reflects
  // that session's member instead of "All members" (`defaultSessionForTeam`).
  await expect(dropdown).toHaveValue('codey')
  expect(jsErrors, `uncaught JS errors: ${jsErrors.join(' | ')}`).toHaveLength(0)
})
