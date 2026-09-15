import { test, expect } from '@playwright/test'
import { installMockInference, mockInferenceState } from './helpers/mockInference'

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

const BLUEPRINTS = {
  object: 'list',
  data: [
    {
      id: 'cli_agent',
      object: 'blueprint',
      name: 'CLI agent',
      description: 'CLI',
      abbreviation: null,
      required_mcp_servers: [],
      tags: [],
      installed: true,
      compiled: true,
      rail: true,
    },
  ],
}

function shotPath(testInfo: { outputDir: string }, name: string): string {
  const root = process.env.ARTIFACTS_DIR || testInfo.outputDir
  return `${root}/${name}`
}

async function stubTeamDropdownPage(page: import('@playwright/test').Page) {
  const stored: { role: string; content: string }[] = []
  await page.route('**/chat/thread**', async (route) => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON() as {
        message?: { role?: string; content?: string }
      }
      if (body.message?.role && body.message.content) {
        stored.push({ role: body.message.role, content: body.message.content })
      }
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        agent_id: 'team-demo-team',
        conversation_id: 'team-demo-team',
        messages: stored,
      }),
    })
  })
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
  await page.route('**/v1/cli-agents**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        clis: ['antigravity', 'grok'],
        installed: ['antigravity', 'grok'],
        configured: ['antigravity', 'grok'],
        native_consensus: {},
        catalog: {},
      }),
    })
  })
  await page.route('**/v1/models**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        object: 'list',
        data: [{ id: 'grok-4', object: 'model', created: 0, owned_by: 'xai' }],
      }),
    })
  })
}

test('team dropdown change is a centred status line and survives reload', async ({
  page,
}, testInfo) => {
  await installMockInference(page)
  await stubTeamDropdownPage(page)

  await page.goto('/chat?team=demo-team')
  const teamSelect = page.getByRole('combobox', { name: 'Team members' })
  // #169: a team chat opens on its nominated seat (Chief of Staff, else the first
  // roster member) — demo-team's first member is Codey — so the transition under
  // test is Codey → Stewie rather than All members → Codey.
  await expect(teamSelect).toHaveValue('codey')
  await page.screenshot({
    path: shotPath(testInfo, 'team_dropdown_before.png'),
    fullPage: true,
  })

  await teamSelect.selectOption('stewie')
  await expect(page).toHaveURL(/[?&]team=demo-team/)
  await expect(page).toHaveURL(/[?&]session=stewie/)
  await expect(teamSelect).toHaveValue('stewie')
  const status = page.getByTestId('chat-status')
  await expect(status).toHaveCount(1)
  await expect(status).toContainText('Team target: Codey (agent/coder) → Stewie (agent/ops)')
  await expect(status).toHaveClass(/os-chat-status/)
  await expect(status).not.toHaveClass(/chat-start|chat-end/)
  await expect(status.locator('.chat-bubble')).toHaveCount(0)
  await page.screenshot({
    path: shotPath(testInfo, 'team_dropdown_status_line.png'),
    fullPage: true,
  })

  await page.reload()
  const restoredSelect = page.getByRole('combobox', { name: 'Team members' })
  await expect(restoredSelect).toHaveValue('stewie')
  await expect(page).toHaveURL(/[?&]session=stewie/)
  await expect(page.getByTestId('chat-status')).toHaveCount(1)
  await expect(page.getByTestId('chat-status')).toContainText(
    'Team target: Codey (agent/coder) → Stewie (agent/ops)',
  )
  await expect(page.getByTestId('chat-status')).not.toHaveClass(/chat-start|chat-end/)

  const composer = page.getByRole('textbox', { name: 'Chat message' })
  await expect(composer).toBeEnabled()
  await composer.fill('after reload still stewie')
  await page.getByRole('button', { name: /^Send$/i }).click()
  await expect.poll(async () => (await mockInferenceState(page)).lastPrompt).toBe(
    'after reload still stewie',
  )
  expect((await mockInferenceState(page)).lastParams).toMatchObject({
    team: 'demo-team',
    target: 'stewie',
  })
})

test('All members clears ?session=, marks ?members=all and survives a reload (#288)', async ({
  page,
}) => {
  await installMockInference(page)
  await stubTeamDropdownPage(page)

  await page.goto('/chat?team=demo-team&session=codey')
  const teamSelect = page.getByRole('combobox', { name: 'Team members' })
  await expect(teamSelect).toHaveValue('codey')
  await teamSelect.selectOption('all')
  await expect(page).toHaveURL(/[?&]team=demo-team/)
  await expect(page).not.toHaveURL(/[?&]session=/)
  await expect(page).toHaveURL(/[?&]members=all/)
  await expect(teamSelect).toHaveValue('all')

  await page.reload()
  // #288: the explicit All members pick rides ?members=all, so it survives the
  // reload instead of re-defaulting to the nominated seat (#169).
  await expect(page.getByRole('combobox', { name: 'Team members' })).toHaveValue('all')
  await expect(page).not.toHaveURL(/[?&]session=/)

  const composer = page.getByRole('textbox', { name: 'Chat message' })
  await expect(composer).toBeEnabled()
  await composer.fill('after reload still all members')
  await page.getByRole('button', { name: /^Send$/i }).click()
  await expect.poll(async () => (await mockInferenceState(page)).lastPrompt).toBe(
    'after reload still all members',
  )
  expect((await mockInferenceState(page)).lastParams).toMatchObject({
    team: 'demo-team',
    target: 'all',
  })
})

test('CLI dropdown change is a bubble-less status line plus carried context', async ({ page }, testInfo) => {
  await page.route('**/chat/thread**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ agent_id: 'cli_agent', conversation_id: 'x', messages: [] }),
    })
  })
  await page.route('**/v1/blueprints**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(BLUEPRINTS),
    })
  })
  await page.route('**/v1/cli-sessions/hop**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        object: 'cli_session_hop',
        status: 'Carried summary context from antigravity → grok (12 tokens).',
        cli_session_id: null,
      }),
    })
  })
  await page.route('**/v1/cli-agents**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        clis: ['antigravity', 'grok'],
        installed: ['antigravity', 'grok'],
        configured: ['antigravity', 'grok'],
        native_consensus: {},
        catalog: {},
      }),
    })
  })
  await page.route('**/v1/models**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'list', data: [] }),
    })
  })

  await page.goto('/chat?blueprint=cli_agent&mode=cli&cli=antigravity')
  const cli = page.getByTestId('routing-pill-agent')
  await expect(cli).toHaveAttribute('data-value', 'antigravity')
  await cli.click()
  await page.getByRole('menuitem', { name: 'grok' }).click()
  const status = page.getByTestId('chat-status')
  await expect(status.first()).toContainText('CLI: antigravity → grok')
  await expect(status.first()).not.toHaveClass(/chat-start|chat-end/)
  await expect(page.getByText(/Carried summary context from antigravity → grok/)).toBeVisible()
  await page.screenshot({
    path: shotPath(testInfo, 'cli_dropdown_status_line.png'),
    fullPage: true,
  })
})
