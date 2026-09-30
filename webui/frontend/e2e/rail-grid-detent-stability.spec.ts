/**
 * #1262 follow-up — the pinned grid must not drift while the rail is dragged.
 *
 * `.os-fav-grid` is `repeat(auto-fill, 5.25rem)` + `justify-content: center`,
 * so the track block re-centres on every sub-pixel rail-width change. When the
 * drag free-tracked between detents the centred tiles visibly slid sideways.
 * The drag now quantizes each frame to the nearest detent
 * (`RAIL_DETENT_ALWAYS`), so two pointer positions inside the same detent
 * produce the same width — and therefore the same tile x — while crossing a
 * detent boundary reflows the columns.
 *
 * jsdom has no layout, so this is a pixel-geometry spec against the built SPA.
 */
import { test, expect, type Page } from '@playwright/test'

const BLUEPRINTS = {
  object: 'list',
  data: [
    { id: 'support', object: 'blueprint', name: 'Support', description: 'Helper', installed: true, compiled: true, rail: true },
    { id: 'codey', object: 'blueprint', name: 'Codey', description: 'Code assistant', installed: true, compiled: true, rail: true },
    { id: 'poet', object: 'blueprint', name: 'Poet', description: 'Words', installed: true, compiled: true, rail: true },
  ],
}

async function stubApis(page: Page) {
  await page.route('**/v1/blueprints**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(BLUEPRINTS) }),
  )
  for (const pattern of ['**/v1/models**', '**/v1/teams**']) {
    await page.route(pattern, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ object: 'list', data: [] }) }),
    )
  }
  await page.route('**/v1/remotes**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ object: 'list', kinds: [], configured: [], data: [] }) }),
  )
  await page.route('**/health**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) }),
  )
  await page.route('**/chat/thread**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ agent_id: 'support', conversation_id: 'grid-detent-e2e', messages: [], summaries: [] }),
    }),
  )
}

function gridSnapshot(page: Page) {
  return page.evaluate(() => {
    const grid = document.querySelector('.os-fav-grid') as HTMLElement
    const rail = document.querySelector('[data-testid="os-agent-rail"]') as HTMLElement
    const cs = getComputedStyle(grid)
    return {
      railWidth: +rail.getBoundingClientRect().width.toFixed(1),
      justifyContent: cs.justifyContent,
      justifyItems: cs.justifyItems,
      columns: cs.gridTemplateColumns.split(' ').length,
      tileLefts: Array.from(grid.querySelectorAll('.os-fav-tile')).map((t) =>
        +t.getBoundingClientRect().left.toFixed(2),
      ),
    }
  })
}

test('#1262 pinned grid only reflows at detent changes during a drag', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.addInitScript(() => {
    localStorage.setItem('swarm_rail_width', '118')
    localStorage.setItem('swarm_pinned_agents', JSON.stringify([
      { id: 'support', name: 'Support' },
      { id: 'codey', name: 'Codey' },
      { id: 'poet', name: 'Poet' },
    ]))
  })
  await stubApis(page)
  await page.goto('/chat')
  await expect(page.getByTestId('os-agent-rail')).toBeVisible()
  await expect(page.locator('.os-fav-grid')).toBeVisible()
  await page.waitForTimeout(300)

  // The live grid is centred as a block.
  const initial = await gridSnapshot(page)
  expect(initial.justifyContent, 'grid block is centred').toBe('center')
  expect(initial.justifyItems, 'tiles are centred in their tracks').toBe('center')

  const hb = await page.getByTestId('rail-resize-handle').boundingBox()
  if (!hb) throw new Error('resize handle has no box')
  const startX = hb.x + hb.width / 2
  const y = hb.y + hb.height / 2
  const dragTo = async (offset: number) => {
    await page.mouse.move(startX, y)
    await page.mouse.down()
    await page.mouse.move(startX + offset, y, { steps: 4 })
    const snap = await gridSnapshot(page)
    await page.mouse.up()
    return snap
  }

  // Two pointer positions inside the 1-col detent gap (its reflow boundary is
  // the 118↔210 midpoint, 164). Both must resolve to the SAME width and the
  // SAME tile x — no incremental drift.
  const a = await dragTo(20)
  const b = await dragTo(40)
  expect(a.railWidth, 'first in-gap drag stays on the 1-col detent').toBe(118)
  expect(b.railWidth, 'second in-gap drag stays on the 1-col detent').toBe(118)
  expect(b.tileLefts, 'tiles do not drift within a detent').toEqual(a.tileLefts)
  expect(a.justifyContent).toBe('center')

  // Crossing the boundary is allowed to reflow (2 columns) — movement is only
  // at detent changes, not continuous.
  const c = await dragTo(60)
  expect(c.railWidth, 'past the midpoint steps to the 2-col detent').toBe(210)
  expect(c.columns, 'column count reflows at the detent').toBe(2)
  expect(c.justifyContent).toBe('center')
})
