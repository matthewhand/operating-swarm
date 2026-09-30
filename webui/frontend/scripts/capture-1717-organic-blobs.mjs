#!/usr/bin/env node
/**
 * #1717 - dark-mode visual proof for the organic blob circle / pill.
 *
 * What this proves, and why it needs a real browser:
 *
 *   1. PATH IN FRAME. The unit tests can only see the `d` string. Whether the
 *      beziers actually trace a smooth closed loop, and whether the curve
 *      bulges past the old `<circle>` / stadium `<rect>`, is a geometry
 *      question the DOM cannot answer. Here the paths are rendered WITH their
 *      viewBox frame, gridlines and Bezier control polygon drawn over them, so
 *      the silhouette can be read against the frame it must stay inside.
 *   2. BEFORE / AFTER. Both columns are in the same shot at the same scale, so
 *      "flatter on one side" is a comparison rather than a claim. The BEFORE
 *      column is the pre-#1717 primitive, hardcoded below, so the comparison
 *      survives future edits to the generator.
 *   3. REAL SIZES. Sidebar is `sm` (2.15rem) and the floating badge / avatar
 *      stack is `xs` (1.5rem) - the two sizes where an organic silhouette
 *      either holds together or degenerates into a squiggle.
 *   4. NO CLIPPING / HIT-TARGET REGRESSION. Measured, not eyeballed: the
 *      browser reports `getBBox()` for the path and `getBoundingClientRect()`
 *      for the rendered avatar, and the script fails if the after-paint box
 *      grows past the before-paint box or if the painted box escapes the
 *      viewBox.
 *
 * The generator is loaded from `src/lib/blobAvatar.ts` itself (transpiled with
 * the esbuild that ships inside Vite) so this can never drift into proving a
 * copy of the art instead of the art.
 *
 *   node scripts/capture-1717-organic-blobs.mjs
 *
 * Writes `docs/screenshots/1717-organic-blobs.{png,html,json}` and prints its
 * measurements as JSON. Exits non-zero on regression.
 */
import { transformWithOxc } from 'vite'
import { chromium } from 'playwright'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'url'
import { CHROMIUM_ARGS, resolveChromium } from './chromiumBinary.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(HERE, '../../..')
const GENERATOR = resolve(HERE, '../src/lib/blobAvatar.ts')
// Same convention as `capture_1391_memory.mjs`: proofs land in docs/screenshots
// so a PR can link them, and the transpiled copy lands in the OS temp dir so
// nothing generated ends up in the tree.
const OUT_DIR = process.env.CAPTURE_OUT || resolve(REPO, 'docs/screenshots')
const OUT_PNG = resolve(OUT_DIR, '1717-organic-blobs.png')
const TMP_MJS = resolve(tmpdir(), 'blobAvatar.1717.mjs')

/**
 * The pre-#1717 primitives, verbatim from `BlobAvatar.tsx` at 6a50fe40. Kept
 * as literal markup rather than re-derived, so the BEFORE column is a fixed
 * reference the generator can never quietly match.
 */
const LEGACY = {
  circle: '<circle cx="20" cy="20" r="15.2" fill="COLOR" />',
  pill: '<rect x="3.2" y="13.2" width="33.6" height="13.6" rx="6.8" fill="COLOR" />',
}

/** Agents chosen because `blobSpecForAgent` hashes them to these shapes. */
const AGENTS = { circle: ['vera', 'reed', 'suki'], pill: ['zed', 'finn'] }

/** Size classes straight out of `src/index.css`. */
const SIZES = [
  { key: 'sidebar', label: 'sidebar row  sm  2.15rem', px: 2.15 * 16 },
  { key: 'badge', label: 'floating badge  xs  1.5rem', px: 1.5 * 16 },
]

/** Sub-pixel slop. The silhouettes are fitted to 0.01 units in the generator. */
const BOX_PX = 0.05

const failures = []
const fail = (msg) => failures.push(msg)

/** Dark theme tokens, copied from the `dark` block in `src/index.css`. */
const THEME = {
  base100: '#161616',
  base200: '#101010',
  base300: '#242424',
  content: '#e6e6e6',
  muted: '#8a8a8a',
  accent: '#4a6fa5',
  ok: '#5cd65c',
}

/** Blobs palette from `src/lib/blobAvatar.ts`, for the per-agent swatches. */
const PALETTE = ['#7C5CBF', '#5CD65C', '#E23B3B', '#3B82F6', '#E84A8A', '#F5A623']

/**
 * Transpile the real generator and import it, so this proof can never drift
 * into proving a copy of the art. `transformWithOxc` is the transform Vite 8
 * itself uses; `transformWithEsbuild` now needs a separately installed esbuild
 * and throws here, which is exactly the "harness that cannot run is a harness
 * that never ran" failure this script has to avoid.
 */
async function loadGenerator() {
  const { code } = await transformWithOxc(readFileSync(GENERATOR, 'utf8'), GENERATOR, {
    lang: 'ts',
  })
  writeFileSync(TMP_MJS, code)
  const mod = await import(pathToFileURL(TMP_MJS).href)
  return { blobSilhouettePath: mod.blobSilhouettePath, blobSpecForAgent: mod.blobSpecForAgent }
}

/** The control polygon + handles, parsed off the generated `d`. */
function controlOverlay(d) {
  const tokens = d.match(/[MCZ]|-?\d+(?:\.\d+)?/g) ?? []
  let i = 0
  const num = () => {
    const v = Number(tokens[i])
    i += 1
    return v
  }
  i += 1
  num()
  num()
  const rows = []
  while (i < tokens.length && tokens[i] === 'C') {
    i += 1
    rows.push({ c1: [num(), num()], c2: [num(), num()], end: [num(), num()] })
  }
  return rows
}

function frame(size, inner, opts = {}) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 40 40" class="frame" xmlns="http://www.w3.org/2000/svg">${inner}</svg>`
}

/** Big path-in-frame panel: viewBox edges, gridlines, and the Bezier skeleton. */
function diagram(d, color, label) {
  const rows = controlOverlay(d)
  const handles = rows
    .map((r) => `<line x1="${r.end[0]}" y1="${r.end[1]}" x2="${r.c1[0]}" y2="${r.c1[1]}" /><line x1="${r.end[0]}" y1="${r.end[1]}" x2="${r.c2[0]}" y2="${r.c2[1]}" />`)
    .join('')
  const anchors = rows.map((r) => `<circle cx="${r.end[0]}" cy="${r.end[1]}" r="0.5" />`).join('')
  const poly = rows.map((r) => `${r.end[0]},${r.end[1]}`).join(' ')
  return `
  <figure class="diagram" data-testid="diagram">
    <svg viewBox="-2 -2 44 44" class="diagram-svg" xmlns="http://www.w3.org/2000/svg">
      <rect x="0" y="0" width="40" height="40" fill="none" stroke="${THEME.accent}" stroke-width="0.35" stroke-dasharray="2 1.4" />
      ${[5, 10, 15, 20, 25, 30, 35]
        .map((v) => `<line x1="${v}" y1="0" x2="${v}" y2="40" /><line x1="0" y1="${v}" x2="40" y2="${v}" />`)
        .join('')}
      <path d="${d}" fill="${color}" fill-opacity="0.9" />
      <g class="handles">${handles}</g>
      <polyline points="${poly}" class="skeleton" />
      <g class="anchors">${anchors}</g>
    </svg>
    <figcaption>${label}</figcaption>
  </figure>`
}

function cell(agentId, shape, d, color, size) {
  const painted = d
    ? `<svg class="avatar" data-testid="avatar" viewBox="0 0 40 40" width="${size.px}" height="${size.px}" xmlns="http://www.w3.org/2000/svg"><g class="os-blob-body"><path d="${d}" fill="${color}" /></g></svg>`
    : `<svg class="avatar" data-testid="avatar" viewBox="0 0 40 40" width="${size.px}" height="${size.px}" xmlns="http://www.w3.org/2000/svg"><g class="os-blob-body">${LEGACY[shape].replace('COLOR', color)}</g></svg>`
  return `<div class="cell" data-shape="${shape}" data-agent="${agentId}">${painted}<span class="tag">${agentId}</span></div>`
}

/** Legacy shape painted as a ghost outline, for the zoomed overlay row. */
function legacyGhost(shape) {
  if (shape === 'circle') {
    return `<circle cx="20" cy="20" r="15.2" fill="none" stroke="${THEME.muted}" stroke-width="0.45" />`
  }
  return `<rect x="3.2" y="13.2" width="33.6" height="13.6" rx="6.8" fill="none" stroke="${THEME.muted}" stroke-width="0.45" />`
}

/**
 * 4x overlay: the old primitive as a grey ghost, the new loop filled on top, in
 * the same frame. This is the shot that actually reads "flatter on one side" --
 * at 1.5rem the lean is real but it is a sub-pixel, and a reviewer should not
 * have to squint to confirm the ticket landed.
 */
function overlay(d, shape, color, label) {
  return `
  <figure class="overlay" data-testid="overlay">
    <svg viewBox="-1 -1 42 42" class="overlay-svg" xmlns="http://www.w3.org/2000/svg">
      ${legacyGhost(shape)}
      <path d="${d}" fill="${color}" fill-opacity="0.88" />
    </svg>
    <figcaption>${label}</figcaption>
  </figure>`
}

function buildHtml(sections) {
  return `<!doctype html>
<html data-theme="dark"><head><meta charset="utf-8"><title>#1717 organic blobs</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 28px 30px 34px; width: 1180px;
    background: ${THEME.base200}; color: ${THEME.content};
    font: 13px/1.45 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  h1 { font-size: 17px; margin: 0 0 2px; letter-spacing: -0.01em; }
  h2 { font-size: 12px; margin: 0 0 10px; color: ${THEME.muted}; text-transform: uppercase; letter-spacing: 0.09em; font-weight: 600; }
  p.lede { margin: 0 0 22px; color: ${THEME.muted}; max-width: 78ch; }
  section { margin-bottom: 24px; }
  .panel { background: ${THEME.base100}; border: 1px solid ${THEME.base300}; border-radius: 12px; padding: 16px 18px; }
  /* path-in-frame grid */
  .diagram { margin: 0; width: 250px; }
  .diagram-svg { width: 100%; display: block; background: ${THEME.base200}; border-radius: 8px; }
  .diagram-svg line { stroke: ${THEME.base300}; stroke-width: 0.25; }
  .diagram-svg .handles line { stroke: #ffffff; stroke-width: 0.18; stroke-opacity: 0.55; }
  .diagram-svg .anchors circle { fill: #ffffff; fill-opacity: 0.95; }
  .diagram-svg .skeleton { fill: none; stroke: ${THEME.ok}; stroke-width: 0.3; }
  figcaption { margin-top: 7px; font-size: 11px; color: ${THEME.muted}; }
  .diagrams { display: flex; gap: 18px; flex-wrap: wrap; }
  .overlays { display: flex; gap: 18px; flex-wrap: wrap; }
  .overlay { margin: 0; width: 250px; }
  .overlay-svg { width: 100%; display: block; background: ${THEME.base200}; border-radius: 8px; }
  .cell { display: flex; flex-direction: column; align-items: center; gap: 5px; }
  .cell .tag { font-size: 10px; color: ${THEME.muted}; }
  .avatar { display: block; overflow: visible; }
  .sidebyside { display: grid; grid-template-columns: 1fr 1fr; gap: 0 26px; align-items: start; }
  .sidebyside h2 { grid-column: 1 / -1; margin-top: 16px; }
  .sidebyside h2:first-child { margin-top: 0; }
  .col { display: flex; flex-direction: column; gap: 9px; }
  .colhead { font-size: 10px; letter-spacing: 0.14em; color: ${THEME.muted}; text-transform: uppercase; }
  .railnote { grid-column: 1 / -1; color: ${THEME.muted}; font-size: 11px; margin: 16px 0 0; }
</style></head>
<body>
  <h1>#1717 - blob theme: organic circle and pill silhouettes</h1>
  <p class="lede">
    Dark mode, real render. The OLD primitive is the pre-#1717 <code>&lt;circle r="15.2"&gt;</code> /
    stadium <code>&lt;rect rx="6.8"&gt;</code>; the NEW silhouette is the generated closed
    cubic-Bezier loop: one side reads flatter, the rest leans a little. Dashed blue is the 40x40
    viewBox frame, green is the Bezier control polygon, white dots are its anchors. Sizes are the
    shipped size classes, not invented ones.
  </p>
  ${sections}
</body></html>`
}

async function main() {
  const { blobSilhouettePath, blobSpecForAgent } = await loadGenerator()

  // 1. Path in frame, one large diagram per agent, plus a 4x ghost overlay.
  const diagramCards = []
  const overlayCards = []
  for (const [shape, ids] of Object.entries(AGENTS)) {
    for (const [index, id] of ids.entries()) {
      const spec = blobSpecForAgent(id)
      if (spec.shape !== shape) {
        fail(`agent "${id}" hashes to ${spec.shape}, not ${shape} - pick a new id for the proof`)
        continue
      }
      const d = blobSilhouettePath(shape, id)
      if (!d) {
        fail(`agent "${id}" produced no organic path for ${shape}`)
        continue
      }
      const color = PALETTE[index % PALETTE.length]
      diagramCards.push(diagram(d, color, `${shape} / ${id}`))
      overlayCards.push(overlay(d, shape, color, `${shape} / ${id} &mdash; ghost is the old primitive`))
    }
  }

  // 2. Before / after at both shipped sizes.
  const beforeAfter = []
  for (const [shape, ids] of Object.entries(AGENTS)) {
    for (const size of SIZES) {
      const before = ids
        .map((id, index) => cell(id, shape, null, PALETTE[index % PALETTE.length], size))
        .join('')
      const after = ids
        .map((id, index) => {
          const d = blobSilhouettePath(shape, id)
          return cell(id, shape, d, PALETTE[index % PALETTE.length], size)
        })
        .join('')
      beforeAfter.push(`
        <div class="sidebyside" data-testid="pair" data-shape="${shape}" data-size="${size.key}">
          <h2>${shape} &middot; ${size.label}</h2>
          <div class="col"><span class="colhead">before</span>${before}</div>
          <div class="col"><span class="colhead">after</span>${after}</div>
        </div>`)
    }
  }

  const html = buildHtml(`
    <section class="panel">
      <h2>4x overlay - old primitive ghosted under the new loop</h2>
      <div class="overlays">${overlayCards.join('')}</div>
    </section>
    <section class="panel">
      <h2>Path in frame - control polygon over the painted loop</h2>
      <div class="diagrams">${diagramCards.join('')}</div>
    </section>
    <section class="panel">
      <h2>Before / after at shipped size classes</h2>
      ${beforeAfter.join('')}
      <p class="railnote">
        Same viewBox, same agent ids, same colours - so any silhouette change is the geometry and
        nothing else. A blob that grew past its box would show as a wider painted column here.
      </p>
    </section>`)

  mkdirSync(OUT_DIR, { recursive: true })
  const htmlPath = resolve(OUT_DIR, '1717-organic-blobs.html')
  writeFileSync(htmlPath, html)

  const browser = await chromium.launch({ executablePath: resolveChromium(), args: CHROMIUM_ARGS })
  const page = await browser.newPage({ viewport: { width: 1180, height: 900 }, deviceScaleFactor: 2 })
  await page.goto(pathToFileURL(htmlPath).href, { waitUntil: 'networkidle' })
  await page.evaluate(() => document.fonts?.ready)

  const measurements = await page.evaluate(() => {
    const read = (el) => {
      const r = el.getBoundingClientRect()
      return { w: r.width, h: r.height }
    }
    const pairs = [...document.querySelectorAll('[data-testid="pair"]')].map((pair) => {
      const cells = [...pair.querySelectorAll('.cell')].map((cell) => {
        const svg = cell.querySelector('svg')
        const body = svg.querySelector('.os-blob-body')
        const paint = body.firstElementChild
        const box = paint.getBBox()
        return {
          shape: cell.dataset.shape,
          agent: cell.dataset.agent,
          // getBBox is in viewBox units; the rendered rect is in CSS px.
          bbox: { x: box.x, y: box.y, w: box.width, h: box.height },
          rect: read(svg),
          tagName: paint.tagName.toLowerCase(),
        }
      })
      return { size: pair.dataset.size, shape: pair.dataset.shape, cells }
    })
    return pairs
  })

  await page.screenshot({ path: OUT_PNG, fullPage: true })
  await browser.close()

  // 3. Regression gate: the painted box must not outgrow the primitive it replaced.
  const LEGACY_BOX = {
    circle: { w: 30.4, h: 30.4 },
    pill: { w: 33.6, h: 13.6 },
  }
  for (const group of measurements) {
    for (let i = 0; i < group.cells.length; i += 1) {
      const after = group.cells[i]
      // cells alternate BEFORE, AFTER per agent index within each column block,
      // so pair them positionally: half the list is BEFORE, half is AFTER.
      const half = group.cells.length / 2
      const before = group.cells[i % half]
      if (i < half) continue
      const legacy = LEGACY_BOX[after.shape]
      const label = `${after.shape}/${after.agent}@${group.size}`
      if (after.bbox.w > legacy.w + BOX_PX) {
        fail(`${label}: painted width grew ${after.bbox.w.toFixed(2)} > ${legacy.w} (viewBox units)`)
      }
      if (after.bbox.h > legacy.h + BOX_PX) {
        fail(`${label}: painted height grew ${after.bbox.h.toFixed(2)} > ${legacy.h} (viewBox units)`)
      }
      if (after.bbox.x < -BOX_PX || after.bbox.y < -BOX_PX) {
        fail(`${label}: painted box escapes the viewBox at (${after.bbox.x.toFixed(2)}, ${after.bbox.y.toFixed(2)})`)
      }
      // The rendered avatar element itself is the hit target; its box must not
      // have moved relative to the old primitive.
      if (Math.abs(after.rect.w - before.rect.w) > BOX_PX) {
        fail(`${label}: rendered avatar width changed ${before.rect.w} -> ${after.rect.w}`)
      }
    }
  }

  const report = {
    issue: 1717,
    theme: 'dark',
    sizes: SIZES.map((s) => ({ key: s.key, px: s.px })),
    agents: AGENTS,
    screenshots: [OUT_PNG, htmlPath],
    measurements,
  }
  writeFileSync(resolve(OUT_DIR, '1717-organic-blobs.json'), `${JSON.stringify(report, null, 2)}\n`)

  console.log(JSON.stringify({ screenshots: report.screenshots, measurements }, null, 2))
  if (failures.length > 0) {
    console.error(`\n#1717 proof FAILED:\n  - ${failures.join('\n  - ')}`)
    process.exitCode = 1
    return
  }
  console.log('\n#1717 proof OK: organic loop matches the old footprint, in frame, at both sizes.')
}

await main()
