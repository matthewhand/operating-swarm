import path from 'node:path'
import { test, expect } from '@playwright/test'
import { artifactsDir } from './helpers/artifacts'

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

const LONG_AGENTS = {
  object: 'list',
  data: [
    ...Array.from({ length: 16 }, (_, i) => ({
      id: `api-${i}`,
      name: `API Agent ${i}`,
      kind: 'api',
      source: `blueprint:api-${i}`,
      placeholder: false,
    })),
    { id: 'grok', name: 'grok', kind: 'cli', source: 'cli:grok', placeholder: false },
    { id: 'claude', name: 'claude', kind: 'cli', source: 'cli:claude', placeholder: false },
    {
      id: 'acp',
      name: 'ACP harness',
      kind: 'remote',
      source: 'placeholder:remote:acp',
      placeholder: true,
    },
  ],
}

type AgentList = typeof AGENTS

async function stubComposerApis(page: import('@playwright/test').Page, agents: AgentList = AGENTS) {
  await page.route('**/v1/team-agents**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(agents),
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

type Box = { top: number; bottom: number; left: number; right: number }

function boxesOverlap(a: Box, b: Box, epsilon = 1): boolean {
  return (
    a.left < b.right - epsilon &&
    b.left < a.right - epsilon &&
    a.top < b.bottom - epsilon &&
    b.top < a.bottom - epsilon
  )
}

async function visibleInScroller(
  page: import('@playwright/test').Page,
  testId: string,
): Promise<Box | null> {
  return page.evaluate((id) => {
    const el = document.querySelector(`[data-testid="${id}"]`)
    const scroller = document.querySelector('[data-testid="available-agents-scroller"]')
    if (!(el instanceof HTMLElement) || !(scroller instanceof HTMLElement)) return null
    const a = el.getBoundingClientRect()
    const b = scroller.getBoundingClientRect()
    const top = Math.max(a.top, b.top)
    const bottom = Math.min(a.bottom, b.bottom)
    const left = Math.max(a.left, b.left)
    const right = Math.min(a.right, b.right)
    if (bottom - top < 1 || right - left < 1) return null
    return { top, bottom, left, right }
  }, testId)
}

const VIEWPORTS = [
  { name: 'desktop', width: 1280, height: 800 },
  { name: 'mobile', width: 375, height: 812 },
] as const

for (const viewport of VIEWPORTS) {
  test(`#100 available agents kinds do not overlap at ${viewport.name} ${viewport.width}x${viewport.height}`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await stubComposerApis(page, LONG_AGENTS)
    await page.goto('/')
    // Rail Teams control is off-canvas on narrow viewports; open via the same
    // event the rail button dispatches so the pane layout is what we assert.
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent('swarm:open-team-composer'))
    })
    await expect(page.getByRole('heading', { name: /new team/i })).toBeVisible()

    const scroller = page.getByTestId('available-agents-scroller')
    await scroller.scrollIntoViewIfNeeded()
    await expect(scroller).toBeVisible()
    await expect(page.getByTestId('available-agents-kind-api')).toHaveText(/API\s*\(16\)/)
    await expect(page.getByTestId('available-agents-kind-cli')).toHaveText(/CLI\s*\(2\)/)
    await expect(page.getByTestId('available-agents-kind-remote')).toHaveText(/remote\s*\(1\)/)

    const overflow = await scroller.evaluate((el) => {
      const style = getComputedStyle(el)
      const lists = [...el.querySelectorAll('[data-testid^="available-agents-group-"] ul')].map(
        (ul) => getComputedStyle(ul).overflowY,
      )
      return { pane: style.overflowY, lists }
    })
    expect(overflow.pane).toBe('auto')
    expect(overflow.lists).toHaveLength(3)
    for (const value of overflow.lists) {
      expect(value === 'visible' || value === 'clip').toBeTruthy()
    }

    const shotDir = artifactsDir()
    await page.getByRole('dialog', { name: /new team/i }).screenshot({
      path: path.join(shotDir, `issue-100-available-${viewport.name}-top.png`),
    })

    const kinds = ['api', 'cli', 'remote'] as const
    const topBoxes = []
    for (const kind of kinds) {
      topBoxes.push(await visibleInScroller(page, `available-agents-kind-${kind}`))
    }
    const visibleTop = topBoxes.filter((box): box is Box => box !== null)
    for (let i = 0; i < visibleTop.length; i += 1) {
      for (let j = i + 1; j < visibleTop.length; j += 1) {
        expect(
          boxesOverlap(visibleTop[i], visibleTop[j]),
          `${viewport.name}: kind headers overlap before scroll`,
        ).toBe(false)
      }
    }

    await scroller.evaluate((el) => {
      el.scrollTop = Math.min(120, el.scrollHeight)
    })
    const apiRow = scroller.getByText('API Agent 0')
    const cliHeader = page.getByTestId('available-agents-kind-cli')
    if ((await apiRow.isVisible()) && (await cliHeader.isVisible())) {
      const apiBox = await apiRow.boundingBox()
      const cliBox = await cliHeader.boundingBox()
      if (apiBox && cliBox) {
        expect(
          boxesOverlap(apiBox, cliBox),
          `${viewport.name}: scrolling API covers CLI`,
        ).toBe(false)
      }
    }

    await scroller.evaluate((el) => {
      el.scrollTop = el.scrollHeight
    })
    await expect(page.getByTestId('available-agents-kind-remote')).toBeVisible()
    await expect(scroller.getByText('ACP harness')).toBeVisible()
    const bottomBoxes = []
    for (const kind of kinds) {
      bottomBoxes.push(await visibleInScroller(page, `available-agents-kind-${kind}`))
    }
    const visibleBottom = bottomBoxes.filter((box): box is Box => box !== null)
    for (let i = 0; i < visibleBottom.length; i += 1) {
      for (let j = i + 1; j < visibleBottom.length; j += 1) {
        expect(
          boxesOverlap(visibleBottom[i], visibleBottom[j]),
          `${viewport.name}: kind headers overlap after scroll`,
        ).toBe(false)
      }
    }

    await page.getByRole('dialog', { name: /new team/i }).screenshot({
      path: path.join(shotDir, `issue-100-available-${viewport.name}-scrolled.png`),
    })
    await testInfo.attach(`issue-100-${viewport.name}`, {
      path: path.join(shotDir, `issue-100-available-${viewport.name}-scrolled.png`),
      contentType: 'image/png',
    })

    await scroller.getByRole('button', { name: 'Add' }).last().click()
    const roster = page.getByRole('list', { name: /roster members/i })
    await expect(roster.getByText('ACP harness')).toBeVisible()
  })
}
