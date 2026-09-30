#!/usr/bin/env node
/**
 * #1695 + #1701 — real-renderer regression guard for the top chrome band.
 *
 * jsdom has no layout engine and no compositor, so the two defects these
 * tickets are about cannot be pinned in a unit test:
 *
 *   #1695 the server/socket popup trigger's glyph rendered 14x16 in a 16px box
 *         (daisyUI's transparent 1px `.btn` border) while the three sibling
 *         footer icons render 16x16 — and its optical centre sat 0.25rem left
 *         of theirs.
 *   #1701 the navbar band paints a solid colour, so `backdrop-filter` has
 *         nothing translucent to blur.
 *
 * MEASURE THE BUILT BUNDLE. `src/index.css` still carries `@tailwind`
 * directives, so pointing a harness at the raw source renders the chrome with
 * none of its compiled utilities and reports confident nonsense. Serve the app
 * (or a preview of `dist/`) and point BASE at it:
 *
 *   npm run build && BASE=http://127.0.0.1:8001 node scripts/measure-top-chrome.mjs
 *
 * Exits non-zero on regression, and says so loudly when the served bundle is
 * older than the source it is supposed to contain.
 */
import { chromium } from 'playwright'
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'url'

const HERE = dirname(fileURLToPath(import.meta.url))
const SRC_CSS = resolve(HERE, '../src/index.css')
const BASE = process.env.BASE || 'http://127.0.0.1:8001'
const PAGE = process.env.PAGE || '/chat'
/** Glyph-centre tolerance in px: sub-pixel only, never a visible drift. */
const CENTRE_TOLERANCE_PX = 0.5

/**
 * Alpha of a computed `background-color`, for both `rgb()/rgba()` and the
 * `color(srgb r g b / a)` form a `color-mix()` resolves to.
 * `null` when the value is not a plain colour.
 */
function backgroundAlpha(value) {
  if (!value || value === 'transparent') return 0
  const slash = /\/(\s*[\d.]+%?)\s*\)/.exec(value)
  if (slash) {
    const raw = slash[1].trim()
    return raw.endsWith('%') ? parseFloat(raw) / 100 : parseFloat(raw)
  }
  const rgb = /^rgba?\(([^)]*)\)$/.exec(value)
  if (!rgb) return null
  const parts = rgb[1].split(/[\s,/]+/).filter(Boolean)
  if (parts.length < 4) return 1
  const raw = parts[3]
  return raw.endsWith('%') ? parseFloat(raw) / 100 : parseFloat(raw)
}

const failures = []
const fail = (msg) => failures.push(msg)

const source = readFileSync(SRC_CSS, 'utf8')
const browser = await chromium.launch()
try {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
  await page.goto(`${BASE}${PAGE}`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(2000)

  const measured = await page.evaluate(() => {
    const box = (el) => {
      const r = el.getBoundingClientRect()
      return { x: r.x, y: r.y, w: r.width, h: r.height, cx: r.x + r.width / 2, cy: r.y + r.height / 2 }
    }
    const footerIds = ['os-teams-button', 'os-plugins-button', 'os-calendar-button', 'rail-server-icon']
    const items = footerIds.map((id) => {
      const el = document.querySelector(`[data-testid="${id}"]`)
      if (!el) return { id, missing: true }
      const glyph = el.querySelector('svg')
      return { id, box: box(el), glyph: glyph ? box(glyph) : null, border: getComputedStyle(el).borderTopWidth }
    })
    const header = document.querySelector('.os-chat-header')
    const headerStyle = header ? getComputedStyle(header) : null
    return {
      items,
      header: header
        ? { background: headerStyle.backgroundColor, backdrop: headerStyle.backdropFilter }
        : null,
    }
  })

  // --- #1695: one icon column in the rail footer -----------------------------
  const glyphs = measured.items.filter((row) => row.glyph)
  if (glyphs.length < 4) {
    fail(`footer icons not measurable (found ${glyphs.length}/4) — is the rail rendered at 1600px?`)
  } else {
    const widths = new Set(glyphs.map((row) => Math.round(row.glyph.w * 100) / 100))
    if (widths.size > 1) {
      fail(`#1695 footer glyphs differ in width: ${glyphs.map((r) => `${r.id}=${r.glyph.w}`).join(' ')}`)
    }
    const centres = glyphs.map((row) => row.glyph.cx)
    const spread = Math.max(...centres) - Math.min(...centres)
    if (spread > CENTRE_TOLERANCE_PX) {
      fail(
        `#1695 footer glyph optical centres span ${spread.toFixed(2)}px ` +
          `(> ${CENTRE_TOLERANCE_PX}): ${glyphs.map((r) => `${r.id}=${r.glyph.cx.toFixed(2)}`).join(' ')}`,
      )
    }
    const trigger = glyphs.find((row) => row.id === 'rail-server-icon')
    if (trigger && trigger.border !== '0px') {
      fail(`#1695 rail-server-icon still paints a ${trigger.border} border — it squeezes the glyph`)
    }
    // "One centreline" is a PITCH, not one y: the four icons stack 2rem apart, so
    // the trigger has to continue the siblings' rhythm exactly.
    const siblings = glyphs.filter((row) => row.id !== 'rail-server-icon')
    if (trigger && siblings.length >= 2) {
      const gaps = siblings.slice(1).map((row, i) => row.glyph.cy - siblings[i].glyph.cy)
      const pitch = gaps.reduce((sum, gap) => sum + gap, 0) / gaps.length
      const expected = siblings[siblings.length - 1].glyph.cy + pitch
      if (Math.abs(trigger.glyph.cy - expected) > CENTRE_TOLERANCE_PX) {
        fail(
          `#1695 the trigger's centreline is off the footer rhythm: at ${trigger.glyph.cy.toFixed(2)}, ` +
            `expected ${expected.toFixed(2)} (${pitch.toFixed(2)}px pitch)`,
        )
      }
    }
  }

  // --- #1701: the band is glass, not a solid strip ---------------------------
  if (!measured.header) {
    fail('.os-chat-header not found — is the chat navbar mounted?')
  } else {
    const { background, backdrop } = measured.header
    const alpha = backgroundAlpha(background)
    if (alpha === null) {
      fail(`#1701 could not read the navbar background colour (${background})`)
    } else if (alpha === 0) {
      fail('#1701 the navbar band has no background at all — the glass tint is not being served')
    } else if (alpha >= 1) {
      fail(`#1701 the navbar background is opaque (${background}) — backdrop-filter cannot blur it`)
    }
    if (!backdrop || backdrop === 'none') {
      fail('#1701 the navbar has no backdrop-filter — content cannot read through it')
    }
  }

  // --- staleness: the served bundle must contain what src/index.css declares --
  if (source.includes('--os-navbar-glass-bg') && (!measured.header || measured.header.backdrop === 'none')) {
    fail(
      'the served stylesheet looks STALE: src/index.css declares the glass tokens but the ' +
        'band has no backdrop-filter. Rebuild (npm run build) before trusting this run.',
    )
  }
} finally {
  await browser.close()
}

if (failures.length) {
  console.error(`top chrome regression (${BASE}${PAGE}):`)
  for (const line of failures) console.error(`  - ${line}`)
  process.exit(1)
}
console.log(`top chrome OK (${BASE}${PAGE})`)
