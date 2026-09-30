/**
 * #1246 / #1289 — collapsing the agent rail must reclaim its width.
 *
 * The rail is in-flow chrome on desktop, and useRailResize mirrors the live
 * width onto the shell root as `--os-rail-width`. A collapsed rail is 0px, so
 * `<main>` stretches instead of leaving a dead gutter. This guards the
 * regression where collapse set `data-collapsed` but the reserved width (and
 * therefore the content gap) stayed put.
 */
import { test, expect } from '@playwright/test'

const BLUEPRINTS = {
  object: 'list',
  data: [
    { id: 'support', object: 'blueprint', name: 'Support', description: 'Helper', installed: true, compiled: true, rail: true },
    { id: 'codey', object: 'blueprint', name: 'Codey', description: 'Code assistant', installed: true, compiled: true, rail: true },
  ],
}

async function stubApis(page: import('@playwright/test').Page) {
  await page.route('**/v1/blueprints**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(BLUEPRINTS),
    }),
  )
  for (const pattern of ['**/v1/models**', '**/v1/teams**']) {
    await page.route(pattern, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ object: 'list', data: [] }),
      }),
    )
  }
  await page.route('**/v1/remotes**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'list', kinds: [], configured: [], data: [] }),
    }),
  )
  await page.route('**/health**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok' }),
    }),
  )
  await page.route('**/chat/thread**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        agent_id: 'support',
        conversation_id: 'rail-reclaim-e2e',
        messages: [],
        summaries: [],
      }),
    }),
  )
}

function shellMetrics(page: import('@playwright/test').Page) {
  return page.evaluate(() => {
    const rail = document.querySelector('[data-testid="os-agent-rail"]') as HTMLElement | null
    const main = document.getElementById('os-main')
    return {
      railWidth: rail ? rail.getBoundingClientRect().width : -1,
      mainWidth: main ? main.getBoundingClientRect().width : -1,
      reserved: getComputedStyle(document.documentElement).getPropertyValue('--os-rail-width').trim(),
    }
  })
}

test('collapsing the desktop rail reclaims the content width; expand restores it', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await stubApis(page)
  await page.goto('/chat')

  const rail = page.getByTestId('os-agent-rail')
  await expect(rail).toBeVisible()
  await expect(rail).toHaveAttribute('data-collapsed', 'false')

  const before = await shellMetrics(page)
  expect(before.railWidth, 'expanded rail reserves width').toBeGreaterThan(0)
  expect(parseFloat(before.reserved), 'shell mirrors the rail width').toBeGreaterThan(0)

  // The rail's absolutely-positioned resize handle sits over the search row's
  // right edge, so the conceal button is not the top hit-target — invoke the
  // button's own handler instead of relying on coordinate hit-testing.
  await page
    .getByTestId('sidebar-conceal')
    .evaluate((el) => (el as HTMLElement).click())
  await expect(rail).toHaveAttribute('data-collapsed', 'true')

  const collapsed = await shellMetrics(page)
  // The aside keeps a 1px separator border; the body is fully collapsed.
  expect(collapsed.railWidth, 'collapsed rail is ~0px').toBeLessThanOrEqual(2)
  expect(collapsed.railWidth).toBeLessThan(before.railWidth)
  expect(parseFloat(collapsed.reserved), 'no dead gutter is reserved').toBe(0)
  expect(
    collapsed.mainWidth,
    'main reclaims the rail width',
  ).toBeGreaterThan(before.mainWidth)

  // The expand affordance is the only way back and can reclaim the same space.
  await page.getByTestId('sidebar-expand').click()
  await expect(rail).toHaveAttribute('data-collapsed', 'false')
  const restored = await shellMetrics(page)
  expect(restored.railWidth).toBeGreaterThan(0)
  expect(restored.mainWidth).toBeLessThan(collapsed.mainWidth)
})
