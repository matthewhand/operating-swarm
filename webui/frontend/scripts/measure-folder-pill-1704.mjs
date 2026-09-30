#!/usr/bin/env node
/**
 * #1704 — real-renderer regression guard for the pill's folder affordance.
 *
 * The ticket's claim is a GEOMETRY claim: revealing "Select folder" must not
 * grow the pill. A DOM-structure test can prove the control is a sibling of the
 * label column instead of a child of it, but it cannot prove the badge does not
 * get taller — jsdom has no layout engine, so every `getBoundingClientRect()`
 * there is 0×0. This script measures the real thing.
 *
 * MEASURE THE BUILT BUNDLE. `src/index.css` still carries `@tailwind`
 * directives, so pointing a harness at the raw source renders the pill with none
 * of its compiled utilities and reports confident nonsense. Build and serve the
 * app (or a preview of `dist/`), then:
 *
 *   npm run build && BASE=http://127.0.0.1:8001 node scripts/measure-folder-pill-1704.mjs
 *
 * What it pins:
 *   1. the pill is the same height at rest and on hover (the reveal is opacity,
 *      so there is no reflow to measure);
 *   2. the folder glyph and the pencil glyph share a centreline and a size;
 *   3. both icons sit inside the pill's action cluster, which is right-aligned
 *      against the pill's own padding edge, and that cluster is a ROW;
 *   4. the control is not back inside the stacked label column;
 *   5. no visible text rides the folder control.
 *
 * A cross-BUILD comparison against the pre-fix text row (the ticket's
 * "height with icons ≤ height with the old text row") belongs to
 * `scripts/capture_1704_folder_pill.mjs`, which has both bundles in hand; this
 * script prints its numbers as JSON so that comparison reads real measurements
 * instead of a remembered one.
 *
 * Exits non-zero on regression.
 */
import { chromium } from 'playwright'
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'url'

const HERE = dirname(fileURLToPath(import.meta.url))
const SRC_CSS = resolve(HERE, '../src/index.css')
const BASE = process.env.BASE || 'http://127.0.0.1:8001'
const PATH_UNSET = '/__proof__/folder-pill-1704?theme=dark&folder=unset'
const PATH_BOUND = '/__proof__/folder-pill-1704?theme=dark&folder=bound'
/** Sub-pixel only. A real line of text is ~15px, so this cannot hide the defect. */
const PX = 0.5
/**
 * daisyUI's `.btn` carries a 1px TRANSPARENT border (the #1695 lesson: it
 * squeezes a 1rem glyph inside a 1rem box), so a control's painted box can sit
 * 1px inside its layout box. Half a pixel of slop beyond that is still
 * sub-pixel to the eye.
 */
const BOX_PX = 1.5

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
        cx: r.x + r.width / 2,
        cy: r.y + r.height / 2,
      }
    }
    const pill = document.querySelector('[data-testid="selected-agent-header"]')
    const actions = document.querySelector('.os-agent-pill__actions')
    const labelColumn = document.querySelector('.os-navbar-identity-text')
    const folder = document.querySelector('[data-testid="os-navbar-workspace-subtitle-unset"]')
    const pencil = [...document.querySelectorAll('.os-agent-pill__actions .os-navbar-edit-btn')].find(
      (el) => el.getAttribute('aria-label')?.startsWith('Edit'),
    )
    const pillStyle = getComputedStyle(pill)
    // Visible text is anything whose rendered box is not the sr-only clip.
    const walker = document.createTreeWalker(pill, NodeFilter.SHOW_TEXT)
    const visibleText = []
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const text = (node.textContent || '').trim()
      if (!text) continue
      const parent = node.parentElement
      if (parent?.closest('.sr-only')) continue
      const range = document.createRange()
      range.selectNodeContents(node)
      const r = range.getBoundingClientRect()
      if (r.width > 0 && r.height > 0) visibleText.push(text)
    }
    return {
      pill: box(pill),
      pillPaddingRight: parseFloat(pillStyle.paddingRight),
      actions: actions ? box(actions) : null,
      actionsDisplay: actions ? getComputedStyle(actions).display : null,
      actionsDirection: actions ? getComputedStyle(actions).flexDirection : null,
      // The stacked label column: `rows` is what makes a taller badge, so it
      // is the number this script reports rather than the pill's own height.
      labelColumn: labelColumn
        ? { ...box(labelColumn), rows: labelColumn.children.length }
        : null,
      folderInLabelColumn: !!folder?.closest('.os-navbar-identity-text'),
      folder: folder ? { box: box(folder), glyph: box(folder.querySelector('svg')), opacity: getComputedStyle(folder).opacity } : null,
      pencil: pencil ? { box: box(pencil), glyph: box(pencil.querySelector('svg')), opacity: getComputedStyle(pencil).opacity } : null,
      visibleText,
    }
  })
}

const browser = await chromium.launch()
let summary = null
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })

  // --- the state the ticket is about: nothing bound, folder icon + pencil -----
  const unset = await measure(page, PATH_UNSET)
  if (!unset.folder) {
    fail('folder affordance not rendered on the unset seat — is the proof harness passing workspaceFolderEditable?')
  }
  if (!unset.pencil) {
    fail('pencil not rendered on the unset seat — the folder icon has nothing to match density against')
  }

  // --- 1. hover changes opacity, not geometry --------------------------------
  let revealedPillH = unset.pill.h
  if (unset.folder) {
    const atRest = unset.pill.h
    await page.hover('[data-testid="selected-agent-header"]')
    await page.waitForTimeout(300)
    const hovered = await page.evaluate(() => {
      const pill = document.querySelector('[data-testid="selected-agent-header"]')
      const folder = document.querySelector('[data-testid="os-navbar-workspace-subtitle-unset"]')
      const r = pill.getBoundingClientRect()
      return {
        pillH: r.height,
        folderOpacity: folder ? getComputedStyle(folder).opacity : null,
        folderH: folder ? folder.getBoundingClientRect().height : null,
      }
    })
    revealedPillH = hovered.pillH
    if (hovered.folderOpacity !== '1') {
      fail(`#1704 hovering the pill did not reveal the folder icon (opacity ${hovered.folderOpacity})`)
    }
    if (Math.abs(hovered.pillH - atRest) > PX) {
      fail(
        `#1704 pill height changed on hover: ${atRest.toFixed(2)}px at rest → ${hovered.pillH.toFixed(2)}px on hover`,
      )
    }
    if (Math.abs(hovered.folderH - unset.folder.box.h) > PX) {
      fail(`#1704 folder control resized on hover: ${unset.folder.box.h.toFixed(2)}px → ${hovered.folderH.toFixed(2)}px`)
    }
  }

  // --- 2. the affordance is not a second label row ---------------------------
  // The bound pill is NOT the control for this claim: a bound seat renders the
  // path as a bottom label inside the column, so it legitimately carries one
  // more row than the unset seat. The comparable control is the SAME pill
  // before/after the reveal (check 1) and, across builds, the pre-fix text row
  // — which `scripts/capture_1704_folder_pill.mjs` measures against a bundle
  // that still has it.
  const bound = await measure(page, PATH_BOUND)
  if (bound.folder) {
    fail('#1704 the unset-folder icon is still rendered on a seat that HAS a folder — it stacks with the path')
  }
  if (unset.labelColumn && bound.labelColumn && unset.labelColumn.rows > bound.labelColumn.rows) {
    fail(
      `#1704 the unset seat stacks more label rows than the bound one: ` +
        `${unset.labelColumn.rows} vs ${bound.labelColumn.rows}`,
    )
  }

  // --- 3. one density: folder glyph == pencil glyph ---------------------------
  if (unset.folder && unset.pencil) {
    if (Math.abs(unset.folder.glyph.w - unset.pencil.glyph.w) > PX) {
      fail(
        `#1704 glyph widths differ: folder ${unset.folder.glyph.w.toFixed(2)}px vs pencil ${unset.pencil.glyph.w.toFixed(2)}px`,
      )
    }
    if (Math.abs(unset.folder.glyph.cy - unset.pencil.glyph.cy) > PX) {
      fail(
        `#1704 glyph centres differ: folder ${unset.folder.glyph.cy.toFixed(2)} vs pencil ${unset.pencil.glyph.cy.toFixed(2)}`,
      )
    }
    if (Math.abs(unset.folder.box.h - unset.pencil.box.h) > PX) {
      fail(
        `#1704 control heights differ: folder ${unset.folder.box.h.toFixed(2)}px vs pencil ${unset.pencil.box.h.toFixed(2)}px`,
      )
    }
    if (unset.folder.glyph.cx >= unset.pencil.glyph.cx) {
      fail('#1704 the folder icon is not left of the pencil — it is stacked or reversed, not a row')
    }
  }

  // --- 4. the cluster is one right-aligned row --------------------------------
  if (!unset.actions) {
    fail('.os-agent-pill__actions not found — the folder control has no cluster to sit in')
  } else {
    // A flex item is blockified, so the COMPUTED value is `flex` whatever the
    // sheet says; the sheet is where `inline-flex` has to be spelled.
    if (!['flex', 'inline-flex'].includes(unset.actionsDisplay)) {
      fail(`#1704 action cluster display is ${unset.actionsDisplay}, expected a flex container`)
    }
    if (!/\.os-agent-pill__actions\s*\{[^}]*display:\s*inline-flex/.test(source)) {
      fail('index.css no longer declares .os-agent-pill__actions { display: inline-flex }')
    }
    if (unset.actionsDirection === 'column') {
      fail('#1704 action cluster is a COLUMN — that is the taller-badge defect, in a new wrapper')
    }
    // Right-aligned: the cluster's right edge is the pill's content edge.
    const rightGap = unset.pill.right - unset.actions.right
    if (Math.abs(rightGap - unset.pillPaddingRight) > BOX_PX) {
      fail(
        `#1704 action cluster is not right-aligned: ${rightGap.toFixed(2)}px from the pill's right edge, ` +
          `expected its ${unset.pillPaddingRight}px padding`,
      )
    }
    // …and it is to the RIGHT of the label column, not stacked under the name.
    if (unset.labelColumn && unset.actions.x <= unset.labelColumn.x) {
      fail(
        `#1704 the action cluster does not sit right of the label column: ` +
          `cluster x=${unset.actions.x.toFixed(2)}, column x=${unset.labelColumn.x.toFixed(2)}`,
      )
    }
    // …and it is not back inside the stacked column, where one child is one line.
    if (unset.folderInLabelColumn) {
      fail('#1704 the folder control is back inside .os-navbar-identity-text — every child there is a line')
    }
  }

  // --- 5. the control paints an icon and no word -----------------------------
  const strayText = unset.visibleText.filter((t) => /select folder/i.test(t))
  if (strayText.length) {
    fail(`#1704 visible "Select folder" text is still painted in the pill: ${JSON.stringify(strayText)}`)
  }

  // --- staleness: the served stylesheet must be the one this file names --------
  if (source.includes('.os-agent-pill__actions') && !unset.actions) {
    fail(
      'the served stylesheet looks STALE: src/index.css declares .os-agent-pill__actions but the DOM has none. ' +
        'Rebuild (npm run build) before trusting this run.',
    )
  }

  summary = {
    rest: unset.pill.h,
    revealed: revealedPillH,
    labelRows: unset.labelColumn?.rows ?? null,
    folderGlyph: unset.folder ? { w: unset.folder.glyph.w, h: unset.folder.glyph.h } : null,
    pencilGlyph: unset.pencil ? { w: unset.pencil.glyph.w, h: unset.pencil.glyph.h } : null,
  }
} finally {
  await browser.close()
}

if (failures.length) {
  console.error(`folder pill regression (${BASE}):`)
  for (const line of failures) console.error(`  - ${line}`)
  process.exit(1)
}
console.log(`folder pill OK (${BASE})`)
console.log(
  `  pill ${summary.rest.toFixed(2)}px at rest / ${summary.revealed.toFixed(2)}px revealed · ` +
    `label column ${summary.labelRows} row(s) · ` +
    `folder glyph ${summary.folderGlyph.w.toFixed(2)}×${summary.folderGlyph.h.toFixed(2)}px · ` +
    `pencil glyph ${summary.pencilGlyph.w.toFixed(2)}×${summary.pencilGlyph.h.toFixed(2)}px`,
)
// Machine-readable, so the cross-build comparison in the capture script reads
// these numbers rather than re-implementing the measurement.
console.log(`OS_1704_JSON=${JSON.stringify(summary)}`)
