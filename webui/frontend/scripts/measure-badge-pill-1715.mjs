#!/usr/bin/env node
/**
 * #1715 — real-renderer regression guard for the floating badge's vertical
 * centering when the seat has no filesystem bound.
 *
 * The ticket's claim is a GEOMETRY claim: a badge carrying ONE label must centre
 * that label in the badge, not park it against the top or the bottom edge as if
 * a second line were present. A DOM test can prove the column really has one
 * child; it cannot prove where that child sits inside the pill, because jsdom
 * has no layout engine and every `getBoundingClientRect()` there is 0×0. This
 * script measures the real thing.
 *
 * MEASURE THE BUILT BUNDLE. `src/index.css` still carries `@tailwind`
 * directives, so pointing a harness at the raw source renders the pill with none
 * of its compiled utilities and reports confident nonsense. Build and serve the
 * app (or a preview of `dist/`), then:
 *
 *   npm run build && BASE=http://127.0.0.1:8001 node scripts/measure-badge-pill-1715.mjs
 *
 * What it pins:
 *   1. the unset seat really is the single-label state the ticket is about
 *      (one row in the label column) — otherwise the rest proves nothing;
 *   2. that lone label's PAINTED TEXT is centred in the badge's content box.
 *      The element box alone is not enough: a flex item that grows to the
 *      column's full height has a centred box with top-aligned text inside it,
 *      which is the exact defect this issue is about;
 *   3. the bound seat (path bound) is still the #1706 multi-line matrix, and it
 *      did not get shorter or taller because of #1715;
 *   4. the `role@rig` multi-line seat is unchanged too;
 *   5. the label's contrast is not the thing that was traded for the centering
 *      (the unset label must still paint in the muted token, not a new colour).
 *
 * Exits non-zero on regression and prints `OS_1715_JSON=` for cross-build
 * comparison, the same contract `scripts/measure-folder-pill-1704.mjs` uses.
 */
import { chromium } from 'playwright'
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'url'

const HERE = dirname(fileURLToPath(import.meta.url))
const SRC_CSS = resolve(HERE, '../src/index.css')
const BASE = process.env.BASE || 'http://127.0.0.1:8001'
const PATH_UNSET = '/__proof__/badge-pill-1715?theme=dark&folder=unset&role=off'
const PATH_BOUND = '/__proof__/badge-pill-1715?theme=dark&folder=bound&role=off'
const PATH_ROLE = '/__proof__/badge-pill-1715?theme=dark&folder=unset&role=on'
/**
 * A single text line is ~24px tall inside a 32px badge, so the acceptance band
 * has to be tight enough to catch a visibly parked label and loose enough to
 * ignore sub-pixel text-metric rounding. 1px is ~4% of the badge height and well
 * under a line; a top-biased label misses it by an order of magnitude.
 */
const CENTER_PX = 1
/** The bound seat is a real layout, so a #1715 no-op there must be near-exact. */
const BOUND_PX = 0.5

const failures = []
const fail = (msg) => failures.push(msg)

const source = readFileSync(SRC_CSS, 'utf8')

async function measure(page, url) {
  await page.goto(`${BASE}${url}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('[data-testid="selected-agent-header"]')
  await page.evaluate(() => document.fonts?.ready)
  return page.evaluate(() => {
    const box = (el) => {
      const r = el.getBoundingClientRect()
      return {
        x: r.x,
        y: r.y,
        w: r.width,
        h: r.height,
        right: r.right,
        bottom: r.bottom,
        cx: r.x + r.width / 2,
        cy: r.y + r.height / 2,
      }
    }
    const pill = document.querySelector('[data-testid="selected-agent-header"]')
    const column = document.querySelector('.os-navbar-identity-text')
    const label = document.querySelector('.os-navbar-identity-label')
    const avatar = document.querySelector('.os-chat-header__avatar-btn, .os-chat-header__avatar')
    const pillStyle = getComputedStyle(pill)
    // The badge's CONTENT box: padding and border stripped, because "centred in
    // the badge" means centred between the padding edges, not between the outer
    // border of a pill whose border is 1px.
    const contentTop = pill.getBoundingClientRect().top + parseFloat(pillStyle.borderTopWidth)
    const contentBottom = pill.getBoundingClientRect().bottom - parseFloat(pillStyle.borderBottomWidth)
    const contentCy = (contentTop + contentBottom) / 2
    // The PAINTED text, not just the element box: a flex item that fills the
    // column has a centred box whose text sits at the top of it.
    const painted = (() => {
      if (!label) return null
      const walker = document.createTreeWalker(label, NodeFilter.SHOW_TEXT)
      let rect = null
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (!(node.textContent || '').trim()) continue
        const range = document.createRange()
        range.selectNodeContents(node)
        const r = range.getBoundingClientRect()
        if (r.width > 0 && r.height > 0 && (!rect || r.height > rect.height)) rect = r
      }
      if (!rect) return null
      return { x: rect.x, y: rect.y, w: rect.width, h: rect.height, cy: rect.y + rect.height / 2 }
    })()
    const columnStyle = column ? getComputedStyle(column) : null
    const labelStyle = label ? getComputedStyle(label) : null
    return {
      pill: box(pill),
      contentCy,
      column: column ? { ...box(column), rows: column.children.length, alignSelf: columnStyle.alignSelf } : null,
      columnDirection: columnStyle?.flexDirection ?? null,
      label: label ? { ...box(label), color: labelStyle.color } : null,
      painted,
      avatar: avatar ? box(avatar) : null,
      textOffset: painted ? painted.cy - contentCy : null,
      pillHeight: pill.getBoundingClientRect().height,
      bottomLabel: !!document.querySelector('[data-testid="os-navbar-workspace-subtitle"]'),
      roleBadge: !!document.querySelector('[data-testid="os-header-role-badge"]'),
    }
  })
}

const browser = await chromium.launch()
let summary = null
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })

  // --- 1. the state the ticket is about --------------------------------------
  const unset = await measure(page, PATH_UNSET)
  if (!unset.column || unset.column.rows !== 1) {
    fail(
      `#1715 the unset proof seat is not the single-label state: ` +
        `${unset.column?.rows ?? 'no'} row(s) in .os-navbar-identity-text. ` +
        'The harness is wrong, not the fix.',
    )
  }
  if (unset.bottomLabel) {
    fail('#1715 the unset seat still renders a path bottom label — not the unset state')
  }
  if (unset.roleBadge) {
    fail('#1715 the unset seat still renders a role badge — not the unset state')
  }
  if (!unset.painted) {
    fail('#1715 the single label painted no text — the centering claim has nothing to measure')
  }

  // --- 2. the lone label is vertically centred in the badge -------------------
  if (unset.painted) {
    const off = Math.abs(unset.textOffset)
    if (off > CENTER_PX) {
      fail(
        `#1715 the lone label is NOT vertically centred in the badge: text centre is ` +
          `${off.toFixed(2)}px off the badge content centre ` +
          `(${unset.textOffset > 0 ? 'below' : 'above'}). ` +
          `label box ${unset.label.h.toFixed(2)}px, text ${unset.painted.h.toFixed(2)}px, ` +
          `column ${unset.column.h.toFixed(2)}px, pill ${unset.pill.h.toFixed(2)}px.`,
      )
    }
    // The label element must not be a stretched box with parked text inside it:
    // an element taller than its own text is exactly the "as if a second line
    // were present" shape the ticket rejects.
    if (unset.label.h - unset.painted.h > CENTER_PX) {
      fail(
        `#1715 the lone label is a stretched box with parked text: element ` +
          `${unset.label.h.toFixed(2)}px vs text ${unset.painted.h.toFixed(2)}px.`,
      )
    }
  }

  // --- 3. the #1706 bound matrix is untouched --------------------------------
  const bound = await measure(page, PATH_BOUND)
  if (bound.column?.rows !== 2) {
    fail(
      `#1715 the bound seat should keep the two-row #1706 matrix (name + path), got ` +
        `${bound.column?.rows ?? 'no'} row(s).`,
    )
  }
  if (!bound.bottomLabel) {
    fail('#1715 the bound seat lost its path bottom label — #1706 regressed')
  }
  if (bound.pillHeight + BOUND_PX < unset.pillHeight) {
    fail(
      `#1715 #1715 changed the badge height of the multi-line state: ` +
        `unset ${unset.pillHeight.toFixed(2)}px vs bound ${bound.pillHeight.toFixed(2)}px. ` +
        'A second row must still be able to make the badge taller.',
    )
  }

  // --- 4. the role@rig seat is untouched too ---------------------------------
  const role = await measure(page, PATH_ROLE)
  if (role.roleBadge !== true) {
    fail('#1715 the role=on proof seat did not render the role@rig badge — that control is void')
  }
  if (role.column?.rows !== 2) {
    fail(
      `#1715 the role@rig seat should keep the two-row #1706 matrix, got ` +
        `${role.column?.rows ?? 'no'} row(s).`,
    )
  }

  // --- 5. the label keeps its muted token (readability in dark mode) ---------
  if (unset.label?.color) {
    if (/^rgba\(\s*0,\s*0,\s*0/.test(unset.label.color)) {
      fail(`#1715 the unset label paints pure black in dark mode: ${unset.label.color}`)
    }
    if (/^rgb\(\s*255/.test(unset.label.color)) {
      fail(`#1715 the unset label paints pure white in dark mode: ${unset.label.color}`)
    }
  }

  // --- staleness: the served stylesheet must be the one this file names -------
  if (source.includes('.os-navbar-identity-text') && !unset.column) {
    fail(
      'the served stylesheet looks STALE: src/index.css declares .os-navbar-identity-text but the DOM has none. ' +
        'Rebuild (npm run build) before trusting this run.',
    )
  }

  summary = {
    unsetRows: unset.column?.rows ?? null,
    unsetPillH: unset.pillHeight,
    unsetLabelTextOffset: unset.textOffset,
    unsetLabelH: unset.label?.h ?? null,
    unsetTextH: unset.painted?.h ?? null,
    unsetLabelColor: unset.label?.color ?? null,
    boundRows: bound.column?.rows ?? null,
    boundPillH: bound.pillHeight,
    roleRows: role.column?.rows ?? null,
  }
} finally {
  await browser.close()
}

if (failures.length) {
  console.error(`badge centering regression (${BASE}):`)
  for (const line of failures) console.error(`  - ${line}`)
  process.exit(1)
}
console.log(`badge centering OK (${BASE})`)
console.log(
  `  unset: ${summary.unsetRows} row(s), pill ${summary.unsetPillH.toFixed(2)}px, ` +
    `label text ${summary.unsetTextOffset.toFixed(2)}px off centre, ` +
    `element ${summary.unsetLabelH.toFixed(2)}px vs text ${summary.unsetTextH.toFixed(2)}px, ` +
    `color ${summary.unsetLabelColor}`,
)
console.log(
  `  bound: ${summary.boundRows} row(s), pill ${summary.boundPillH.toFixed(2)}px · ` +
    `role=on: ${summary.roleRows} row(s)`,
)
console.log(`OS_1715_JSON=${JSON.stringify(summary)}`)
