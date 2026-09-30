/**
 * Rail geometry at laptop viewports.
 *
 * Two defects shipped together at <= 1440px:
 *  1. The laptop default rail was 97px (AVATAR_ONLY_THRESHOLD + 1), which is
 *     above the avatar-only line (so labels render) but narrower than the
 *     rail's horizontal chrome: the "Routines"/"Plugins" footer labels bled
 *     past the rail's right edge into the chat pane.
 *  2. The absolutely-positioned resize handle (18px wide, 8px over the chat
 *     pane, z-index 50) covered the collapse control in the search row, so a
 *     normal click hit the resizer instead of the button.
 *
 * These are pixel-geometry assertions on purpose — jsdom has no layout, so the
 * unit suite only pins the width contract and the CSS stacking rule. This spec
 * proves the rendered result at the two laptop viewports.
 */
import { test, expect, type Page } from '@playwright/test'

const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
]

const BLUEPRINTS = {
  object: 'list',
  data: [
    { id: 'support', object: 'blueprint', name: 'Support', description: 'Helper', installed: true, compiled: true, rail: true },
    { id: 'codey', object: 'blueprint', name: 'Codey', description: 'Code assistant', installed: true, compiled: true, rail: true },
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
      body: JSON.stringify({ agent_id: 'support', conversation_id: 'rail-geometry-e2e', messages: [], summaries: [] }),
    }),
  )
}

for (const viewport of VIEWPORTS) {
  test(`rail geometry at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await stubApis(page)
    await page.goto('/chat')

    const rail = page.getByTestId('os-agent-rail')
    await expect(rail).toBeVisible()
    await expect(rail).toHaveAttribute('data-avatar-only', 'false')

    const m = await page.evaluate(() => {
      const railEl = document.querySelector('[data-testid="os-agent-rail"]') as HTMLElement
      const railRect = railEl.getBoundingClientRect()
      const label = (sel: string) => {
        const el = document.querySelector(sel) as HTMLElement | null
        if (!el) return null
        const r = el.getBoundingClientRect()
        return { right: r.right, display: getComputedStyle(el).display }
      }
      const button = (sel: string) => {
        const el = document.querySelector(sel) as HTMLElement | null
        if (!el) return null
        return { clientWidth: el.clientWidth, scrollWidth: el.scrollWidth }
      }
      const doc = document.documentElement
      const conceal = document.querySelector('[data-testid="sidebar-conceal"]') as HTMLElement | null
      let concealHit: string | null = null
      if (conceal) {
        const r = conceal.getBoundingClientRect()
        const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
        concealHit = hit ? (hit.closest('[data-testid]')?.getAttribute('data-testid') ?? hit.tagName) : null
      }
      return {
        doc: { scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth },
        railRight: railRect.right,
        railWidth: railRect.width,
        calendarLabel: label('.os-calendar-label'),
        pluginsLabel: label('.os-plugins-label'),
        calendarButton: button('[data-testid="os-calendar-button"]'),
        pluginsButton: button('[data-testid="os-plugins-button"]'),
        concealHit,
      }
    })

    // 1. No horizontal page overflow at laptop widths.
    expect(m.doc.scrollWidth, 'documentElement must not overflow horizontally').toBeLessThanOrEqual(m.doc.clientWidth)

    // 2. The default laptop rail is the one-column detent, non-avatar-only.
    expect(m.railWidth, 'one-column laptop default').toBe(118)
    expect(m.calendarLabel?.display, 'Routines label renders at the laptop default').not.toBe('none')

    // 3. Footer labels stay inside the rail's right edge.
    const tolerance = 0.5
    expect(m.calendarLabel!.right, 'Routines label right edge inside rail').toBeLessThanOrEqual(m.railRight + tolerance)
    expect(m.pluginsLabel!.right, 'Plugins label right edge inside rail').toBeLessThanOrEqual(m.railRight + tolerance)

    // 4. The footer buttons do not internally overflow either.
    expect(m.calendarButton!.scrollWidth, 'Routines button content fits').toBeLessThanOrEqual(m.calendarButton!.clientWidth)
    expect(m.pluginsButton!.scrollWidth, 'Plugins button content fits').toBeLessThanOrEqual(m.pluginsButton!.clientWidth)

    // 5. The collapse control wins the hit-test against the resize handle.
    expect(m.concealHit, 'elementFromPoint at the collapse centre is the button').toBe('sidebar-conceal')

    // 6. A real click toggles the rail (would time out if the resizer occluded).
    await page.getByTestId('sidebar-conceal').click()
    await expect(rail).toHaveAttribute('data-collapsed', 'true')
    await page.getByTestId('sidebar-expand').click()
    await expect(rail).toHaveAttribute('data-collapsed', 'false')
  })
}

/**
 * #1308 follow-up — the one-column footer row and the collapsed right edge.
 *
 * Both defects were horizontal-overflow bugs that only showed once the rail
 * crossed to the 118px detent (footer chrome wider than the pane) or docked
 * right (chrome hanging off the viewport's right edge). unit tests pin the CSS
 * contract; these prove the rendered geometry.
 */
for (const viewport of VIEWPORTS) {
  test(`rail footer stays in-pane at ${viewport.width} (right-docked)`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.addInitScript(() => {
      localStorage.setItem('swarm_rail_side', 'right')
    })
    await stubApis(page)
    await page.goto('/chat')

    const rail = page.getByTestId('os-agent-rail')
    await expect(rail).toBeVisible()
    await expect(rail).toHaveAttribute('data-avatar-only', 'false')

    const m = await page.evaluate(() => {
      const doc = document.documentElement
      const railRect = document.querySelector('[data-testid="os-agent-rail"]')!.getBoundingClientRect()
      const row = document.querySelector('.os-rail-hostname-row') as HTMLElement
      const chrome = document.querySelector('[data-testid="rail-update-chrome"]') as HTMLElement
      return {
        doc: { scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth },
        railRight: railRect.right,
        row: { clientWidth: row.clientWidth, scrollWidth: row.scrollWidth },
        chromeRight: chrome.getBoundingClientRect().right,
      }
    })

    expect(m.doc.scrollWidth, 'right-docked rail must not scroll the page').toBeLessThanOrEqual(m.doc.clientWidth)
    expect(m.row.scrollWidth, 'footer hostname row fits the pane').toBeLessThanOrEqual(m.row.clientWidth)
    expect(m.chromeRight, 'update chip stays inside the rail').toBeLessThanOrEqual(m.railRight + 0.5)
  })

  test(`collapsed right-docked resizer stays on-screen at ${viewport.width}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.addInitScript(() => {
      localStorage.setItem('swarm_rail_side', 'right')
      localStorage.setItem('swarm_rail_width', '0')
    })
    await stubApis(page)
    await page.goto('/chat')

    const rail = page.getByTestId('os-agent-rail')
    await expect(rail).toHaveAttribute('data-collapsed', 'true')

    const m = await page.evaluate(() => {
      const doc = document.documentElement
      const handle = document.querySelector('[data-testid="rail-resize-handle"]')!.getBoundingClientRect()
      return {
        doc: { scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth },
        handleRight: handle.right,
        viewport: window.innerWidth,
      }
    })
    expect(m.doc.scrollWidth, 'collapsed right rail must not scroll the page').toBeLessThanOrEqual(m.doc.clientWidth)
    expect(m.handleRight, 'collapsed resize handle stays on-screen').toBeLessThanOrEqual(m.viewport + 0.5)
  })
}

/* ── #1309 ────────────────────────────────────────────────────────────────
 * D1 name legibility, D2 footer update-chrome hit-target + containment, and
 * D7 collapse→expand restoring the viewport default. Long blueprint names
 * force the name to need width (the old 18px clientWidth / 0px opaque fade).
 * ───────────────────────────────────────────────────────────────────────── */
const LONG_BLUEPRINTS = {
  object: 'list',
  data: [
    { id: 'support', object: 'blueprint', name: 'Support Helper Agent', description: 'Helper with a long name', installed: true, compiled: true, rail: true },
    { id: 'codey', object: 'blueprint', name: 'Codey The Coding Companion', description: 'Code assistant', installed: true, compiled: true, rail: true },
  ],
}

async function stubLongApis(page: Page) {
  await page.route('**/v1/blueprints**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(LONG_BLUEPRINTS) }),
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
      body: JSON.stringify({ agent_id: 'support', conversation_id: 'rail-1309-e2e', messages: [], summaries: [] }),
    }),
  )
}

async function railDefectSnapshot(page: Page) {
  return page.evaluate(() => {
    const doc = document.documentElement
    const rail = document.querySelector('[data-testid="os-agent-rail"]') as HTMLElement
    const railRect = rail.getBoundingClientRect()
    const name = document.querySelector('[data-testid="rail-agent-name"]') as HTMLElement
    const cs = getComputedStyle(name)
    const mask = (cs.maskImage || cs.webkitMaskImage) || ''
    // The bounded fade is min(0.5rem, 40%); 0.5rem = 8px at the 16px root.
    const fade = Math.min(8, 0.4 * name.clientWidth)
    const btn = document.querySelector('[data-testid="rail-update-chrome"]') as HTMLElement | null
    let btnHit: string | null = null
    if (btn) {
      const r = btn.getBoundingClientRect()
      const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
      btnHit = hit ? (hit.closest('[data-testid]')?.getAttribute('data-testid') ?? hit.tagName) : null
    }
    return {
      doc: { scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth },
      rail: { right: railRect.right, width: railRect.width },
      name: {
        clientWidth: name.clientWidth,
        scrollWidth: name.scrollWidth,
        visibleWidth: name.clientWidth - fade,
        mask,
      },
      btnHit,
    }
  })
}

for (const viewport of VIEWPORTS) {
  for (const side of ['left', 'right'] as const) {
    test(`#1309 rail defects at ${viewport.width}x${viewport.height} ${side}`, async ({ page }) => {
      await page.addInitScript((s) => {
        localStorage.setItem('swarm_rail_side', s)
        // The idle update chrome opens the issues URL via window.open; keep it
        // in-page so the click test does not spawn a popup.
        window.open = () => null
      }, side)
      await page.setViewportSize(viewport)
      await stubLongApis(page)
      await page.goto('/chat')

      const rail = page.getByTestId('os-agent-rail')
      await expect(rail).toBeVisible()
      await expect(rail).toHaveAttribute('data-avatar-only', 'false')
      await page.getByTestId('rail-agent-name').first().waitFor()

      const before = await railDefectSnapshot(page)

      // D1: the laptop default is the one-column detent.
      expect(before.rail.width, 'laptop default rail').toBe(118)
      // D1: the name keeps a real run and the opaque region covers the glyphs.
      // Before #1309: clientWidth ~18px, opaque region <= 0px.
      expect(before.name.clientWidth, 'name has a real run').toBeGreaterThanOrEqual(36)
      expect(before.name.visibleWidth, 'opaque region covers the glyphs').toBeGreaterThanOrEqual(28)

      // D2: no horizontal page overflow in either dock (right dock used to
      // overflow by 5px).
      expect(before.doc.scrollWidth, 'no horizontal overflow').toBeLessThanOrEqual(before.doc.clientWidth)
      // D2: the update button wins the hit-test against the resize handle.
      expect(before.btnHit, 'elementFromPoint at the update centre is the button').toBe('rail-update-chrome')

      // D2: a real click is not occluded (would time out under the handle).
      await page.getByTestId('rail-update-chrome').click()

      // D7: collapse → expand restores the viewport default (118), not 256.
      await page.getByTestId('sidebar-conceal').click()
      await expect(rail).toHaveAttribute('data-collapsed', 'true')
      await page.getByTestId('sidebar-expand').click()
      await expect(rail).toHaveAttribute('data-collapsed', 'false')

      const after = await railDefectSnapshot(page)
      expect(after.rail.width, 'expand restores the laptop default').toBe(118)
      expect(after.doc.scrollWidth, 'still no overflow after expand').toBeLessThanOrEqual(after.doc.clientWidth)
    })
  }
}
