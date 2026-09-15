import { test, expect } from '@playwright/test'

const AGENTS = {
  object: 'list',
  data: [
    { id: 'jeeves', name: 'Jeeves', kind: 'api', source: 'blueprint:jeeves', placeholder: false },
    { id: 'grok', name: 'grok', kind: 'cli', source: 'cli:grok', placeholder: false },
    {
      id: 'acp',
      name: 'ACP harness',
      kind: 'remote',
      source: 'placeholder:remote:acp',
      placeholder: true,
    },
  ],
}

async function stubComposerApis(page: import('@playwright/test').Page) {
  await page.route('**/v1/team-agents**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(AGENTS),
    })
  })
  await page.route('**/v1/team-rosters**', async (route) => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON()
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'research-squad',
          object: 'team_roster',
          name: body?.name ?? 'research-squad',
          members: body?.members ?? [],
          wires: body?.wires ?? { handoff: true, as_tool: true },
          chief_of_staff_id: body?.chief_of_staff_id ?? null,
          chief_of_staff_instructions: body?.chief_of_staff_instructions ?? '',
        }),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'list', data: [] }),
    })
  })
  await page.route('**/v1/blueprints**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'list', data: [] }),
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
}

test(' + opens two-pane team composer; add/remove and save roster', async ({ page }) => {
  const jsErrors: string[] = []
  page.on('pageerror', (e) => jsErrors.push(e.message))
  await stubComposerApis(page)
  await page.goto('/')

  await expect(page.getByRole('navigation', { name: 'Primary' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: /^Home$/ })).toHaveCount(0)
  await expect(page.getByRole('link', { name: /^Chat$/ })).toHaveCount(0)
  // Grok chrome: no SPA /teams tab. Django Teams stays on the composer + menu.
  await expect(page.getByRole('link', { name: 'Teams', exact: true })).toHaveCount(0)

  // The composer entry point moved to the rail footer (Teams, directly above
  // Plugins) instead of a navbar "Compose team" button.
  await page.getByTestId('os-teams-button').click()
  await expect(page.getByRole('heading', { name: /new team/i })).toBeVisible()

  const drop = page.getByTestId('team-drop-zone')
  await expect(drop).toBeVisible()
  await expect(drop).toHaveText(/drop agents here/i)

  const available = page.getByRole('list', { name: /available agents list/i })
  await expect(available.getByText('Jeeves')).toBeVisible()
  await expect(available.getByText('API').first()).toBeVisible()
  await expect(available.getByText('CLI').first()).toBeVisible()
  await expect(available.getByText('remote').first()).toBeVisible()

  await expect(page.getByRole('checkbox', { name: /handoff/i })).toBeChecked()
  await expect(page.getByRole('checkbox', { name: /as_tool/i })).toBeChecked()
  await expect(page.getByText(/gate is unwired/i)).toBeVisible()

  const cos = page.getByTestId('team-cos-select')
  await expect(cos).toBeDisabled()
  await expect(page.getByText(/add agents first/i)).toBeVisible()

  await available.getByRole('button', { name: 'Add' }).first().click()
  const roster = page.getByRole('list', { name: /roster members/i })
  // Each roster row carries the id and the display name, so scope to the first.
  await expect(roster.getByText('jeeves').first()).toBeVisible()
  await expect(roster.getByText('API').first()).toBeVisible()
  await expect(cos).toBeEnabled()
  await expect(cos).toHaveValue('')

  await cos.selectOption('jeeves')
  const brief = page.getByTestId('team-cos-instructions')
  await expect(brief).toBeEnabled()
  await brief.fill('prefer grok_agent for revision control')

  await page.getByLabel(/team name/i).fill('research-squad')
  await page.getByRole('button', { name: /save roster/i }).click()
  // Several live regions exist (toasts, meter) — target the save confirmation.
  await expect(
    page.getByRole('status').filter({ hasText: /team_rosters\.json/i }),
  ).toBeVisible()
  await expect(cos).toHaveValue('jeeves')
  await expect(brief).toHaveValue('prefer grok_agent for revision control')

  expect(jsErrors, `uncaught JS errors: ${jsErrors.join(' | ')}`).toHaveLength(0)
})
