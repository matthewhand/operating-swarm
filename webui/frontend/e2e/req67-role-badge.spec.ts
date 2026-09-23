import { test, expect } from '@playwright/test'

const ROLE_ACCENT_COLORS = ['#3d8f8a', '#c47a3a', '#7a6b9b', '#4f8ec9', '#c9a227', '#8a5a9b']

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
      id: 'cos',
      object: 'blueprint',
      name: 'Pat',
      description: 'Talks to any team.',
      abbreviation: null,
      required_mcp_servers: [],
      tags: [],
      installed: true,
      compiled: true,
      role: 'chief_of_staff',
    },
  ],
}

async function stubAgentApis(page: import('@playwright/test').Page) {
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
  await page.route('**/v1/team-rosters**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'list', data: [] }),
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
}

function assertNoRoleAccent(boxShadow: string, background: string, outline: string) {
  const chrome = `${boxShadow} ${background} ${outline}`.toLowerCase()
  for (const color of ROLE_ACCENT_COLORS) {
    expect(chrome, `row chrome should not use role colour ${color}`).not.toContain(color)
  }
}

test('REQ-67: role colour is the badge only; selected/hover stay', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('swarm_hidden_agents', '[]')
  })
  await stubAgentApis(page)
  await page.goto('/chat?blueprint=codey')

  const list = page.getByRole('navigation', { name: 'Agent list' })
  // Support is the seeded favourite tile, so it renders as a pin tile rather than
  // a conversation row (REQ-94: a pin is a move, not a copy).
  const support = page.getByLabel('Pinned agents').getByRole('link', { name: /Support/ })
  // Scope rows by id: the Safety seat is blueprint `gate`, and the seeded demo
  // teams include a "Demo SDLC Skeptic Loop" whose name also matches /Skeptic/.
  const gate = list.locator('a[data-agent-id="gate"]')
  const skeptic = list.locator('a[data-agent-id="skeptic"]')
  const cos = list.locator('a[data-agent-id="cos"]')
  const codey = list.locator('a[data-agent-id="codey"]')

  await expect(support).toBeVisible()
  await expect(gate).toBeVisible()
  await expect(skeptic).toBeVisible()
  await expect(cos).toBeVisible()
  await expect(codey).toBeVisible()

  // The tile carries the same REQ-67 contract as a row: role colour on the badge
  // only, never on the tile chrome.
  await expect(support).toHaveClass(/os-fav-tile/)
  await expect(support).not.toHaveClass(/os-agent-role-/)
  const supportTileStyles = await support.evaluate((el) => {
    const computed = getComputedStyle(el)
    return {
      boxShadow: computed.boxShadow,
      background: computed.backgroundColor,
      outline: computed.outlineColor,
    }
  })
  assertNoRoleAccent(supportTileStyles.boxShadow, supportTileStyles.background, supportTileStyles.outline)

  for (const row of [gate, skeptic, cos, codey]) {
    await expect(row).toHaveClass(/os-agent-row/)
    await expect(row).not.toHaveClass(/os-agent-row--(support|gate|skeptic|cos|chief_of_staff)/)
    await expect(row).not.toHaveClass(/os-agent-role-/)
    const styles = await row.evaluate((el) => {
      const computed = getComputedStyle(el)
      return {
        boxShadow: computed.boxShadow,
        background: computed.backgroundColor,
        outline: computed.outlineColor,
      }
    })
    assertNoRoleAccent(styles.boxShadow, styles.background, styles.outline)
  }

  await expect(support.locator('.os-agent-role-badge')).toHaveAttribute('data-role', 'support')
  await expect(gate.locator('.os-agent-role-badge')).toHaveAttribute('data-role', 'gate')
  await expect(skeptic.locator('.os-agent-role-badge')).toHaveAttribute('data-role', 'skeptic')
  await expect(cos.locator('.os-agent-role-badge')).toHaveAttribute('data-role', 'chief_of_staff')
  await expect(codey.locator('.os-agent-role-badge')).toHaveCount(0)

  const supportBadgeColor = await support.locator('.os-agent-role-badge').evaluate((el) => {
    return getComputedStyle(el).color
  })
  expect(supportBadgeColor).toBe('rgb(61, 143, 138)') // #3d8f8a

  await expect(codey).toHaveClass(/os-agent-row--active/)
  await expect(support).not.toHaveClass(/os-fav-tile--active/)

  const idleBg = await support.evaluate((el) => getComputedStyle(el).backgroundColor)
  await support.hover()
  const hoverBg = await support.evaluate((el) => getComputedStyle(el).backgroundColor)
  expect(hoverBg).not.toBe(idleBg)
  const hoverChrome = await support.evaluate((el) => {
    const computed = getComputedStyle(el)
    return `${computed.boxShadow} ${computed.backgroundColor}`
  })
  for (const color of ROLE_ACCENT_COLORS) {
    expect(hoverChrome.toLowerCase()).not.toContain(color)
  }
})
