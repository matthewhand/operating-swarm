/**
 * Pinned-grid column geometry, measured in a real browser.
 *
 * The requirement (#1289 follow-up): resizing the sidepane must take the
 * pinned grid from 1 agent column to 2 to 3, and tiles 1 and 2 must NOT move
 * horizontally while it does.
 *
 * That holds only if a tile's x is a function of its index alone:
 *
 *     x(i) = margin + i * (track + gap)
 *
 * With `justify-content: center` the *track set* is centred, so
 * x(i) = (W - tracksWidth) / 2 + i * (track + gap) — a function of the
 * container width, which is exactly the sideways wobble. jsdom has no layout
 * engine, so this cannot be asserted in vitest; it needs a real renderer.
 *
 * Loads the real `src/index.css` and the real tile class names, sweeps the rail
 * width, and reports the column count and every tile's x. Exits non-zero if
 * tiles 1 or 2 move horizontally, so it doubles as a regression gate.
 *
 * #1683 also audits the free-tracking band per pin count (see `BY_PINS` below),
 * which is the browser-side half of the detent rule: the unit tests prove the
 * rule's arithmetic, this proves the rule's premise holds in a real layout.
 *
 * Usage: node scripts/measure-pinned-grid.mjs [--json] [--shots <dir>]
 */
import { chromium } from 'playwright'
import { mkdirSync, writeFileSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { CHROMIUM_ARGS, resolveChromium } from './chromiumBinary.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const ROOT = join(HERE, '..')
const CSS = readFileSync(join(ROOT, 'src', 'index.css'), 'utf8')
const jsonOut = process.argv.includes('--json')
const shotIdx = process.argv.indexOf('--shots')
const SHOTS = shotIdx > -1 ? process.argv[shotIdx + 1] : null

// Mirrors railResize.ts: track 5.25rem @16px, gap 0.5rem, margin 0.75rem.
const DETENTS = [88, 118, 210, 302, 394, 420]
const TILES = 6
/**
 * #1683 — the pin counts the detent rule is defined over, and the rigid/free
 * split that follows from them. The rule (railResize.ts `railSnapPointsForPins` /
 * `topColumnDetent`) says: the column detents are the widths that exactly fit
 * `1..min(pins, 4)` columns, and the rail free-tracks STRICTLY ABOVE the
 * topmost one.
 *
 * The claim that makes free-tracking safe there is a browser fact, not a unit
 * test — jsdom has no layout engine. It is: a tile's column is `index % cols`, so
 * a tile moves sideways exactly when `cols` changes AND `index >= cols`. At or
 * above `railWidthForColumns(pins)` every pin has `index < cols`, so widening
 * only appends empty tracks and no pin moves. Below it, `cols < pins` for some
 * pin and that pin jumps on every boundary — the #1262 wobble.
 *
 * `--by-pins` measures exactly that, per pin count, and FAILS if any pin's x
 * moves inside its own free band.
 */
const BY_PINS = [0, 1, 2, 3, 4, 5]

const page_html = (tiles = TILES) => `<!doctype html><html data-theme="dark"><head><meta charset="utf-8">
<style>${CSS}
/* Harness-only: the rail container the grid lives in. */
body{margin:0;background:#111}
.rail{width:var(--w);overflow:hidden}
</style></head><body>
<div class="rail" id="rail"><div class="os-fav-grid" id="grid" data-testid="agent-fav-grid">
${Array.from({ length: tiles }, (_, i) => `<div class="os-fav-tile group/tile" data-i="${i}">${i}</div>`).join('')}
</div></div></body></html>`

const browser = await chromium.launch({
  executablePath: resolveChromium(),
  args: CHROMIUM_ARGS,
})
const page = await browser.newPage({ viewport: { width: 900, height: 700 } })
await page.setContent(page_html(), { waitUntil: 'load' })

async function measure(width) {
  return page.evaluate((w) => {
    const rail = document.getElementById('rail')
    rail.style.setProperty('--w', `${w}px`)
    const grid = document.getElementById('grid')
    const tracks = getComputedStyle(grid).gridTemplateColumns
    const cols = tracks.split(' ').filter(Boolean).length
    const tiles = [...grid.querySelectorAll('.os-fav-tile')].map((el) => {
      const r = el.getBoundingClientRect()
      return { i: Number(el.dataset.i), x: Math.round(r.x * 100) / 100, w: Math.round(r.width * 100) / 100 }
    })
    const gridRect = grid.getBoundingClientRect()
    return {
      railWidth: w,
      cols,
      gridX: Math.round(gridRect.x * 100) / 100,
      justifyContent: getComputedStyle(grid).justifyContent,
      tiles,
    }
  }, width)
}

const sweep = []
for (let w = 88; w <= 420; w += 1) sweep.push(await measure(w))
for (const w of DETENTS) {
  if (!sweep.some((r) => r.railWidth === w)) sweep.push(await measure(w))
}
sweep.sort((a, b) => a.railWidth - b.railWidth)

if (SHOTS) mkdirSync(SHOTS, { recursive: true })
const shots = []
for (const w of DETENTS) {
  await page.evaluate((ww) => document.getElementById('rail').style.setProperty('--w', `${ww}px`), w)
  if (SHOTS) {
    const p = join(SHOTS, `pinned-grid-${w}px.png`)
    await page.locator('#rail').screenshot({ path: p })
    shots.push(p)
  }
}

// The invariant: while >= 2 columns fit, tiles 1 and 2 never move sideways.
const multi = sweep.filter((r) => r.cols >= 2)
const violations = []
for (const i of [0, 1]) {
  const xs = [...new Set(multi.map((r) => r.tiles[i]?.x).filter((v) => v !== undefined))]
  if (xs.length > 1) {
    violations.push({ tile: i + 1, distinctX: xs.sort((a, b) => a - b), sample: multi.filter((r) => r.tiles[i]?.x === xs[0]).slice(0, 1) })
  }
}

const byDetent = DETENTS.map((w) => {
  const r = sweep.find((s) => s.railWidth === w)
  return r ? { railWidth: w, cols: r.cols, tileX: r.tiles.slice(0, 3).map((t) => t.x) } : { railWidth: w, missing: true }
})

/**
 * #1683 — per-pin-count wobble audit.
 *
 * For each pin count: mount exactly that many tiles, sweep every width, and
 * split the sweep at the pin count's topmost column detent (the width the
 * detent rule makes rigid). Then assert the two halves behave differently:
 *
 *   FREE band (width > topmost): every PINNED tile's x must be constant.
 *     This is the claim that lets the rail free-track. If it fails, the tiles
 *     wobble under the cursor and `RAIL_DETENT_ALWAYS` must extend upward.
 *   RIGID band (width <= topmost): at least one pinned tile's x MUST vary —
 *     otherwise the wobble guard has nothing to defend and #1262's premise is
 *     wrong. (At 1 pin the rigid band is the whole collapse zone, where the grid
 *     is one column wide for every width, so the guard is vacuous there; that is
 *     reported, not failed.)
 */
const byPins = []
for (const pins of BY_PINS) {
  await page.setContent(page_html(Math.max(pins, 1)), { waitUntil: 'load' })
  const rows = []
  for (let w = 88; w <= 420; w += 1) {
    rows.push(await page.evaluate((width) => {
      document.getElementById('rail').style.setProperty('--w', `${width}px`)
      const grid = document.getElementById('grid')
      const cols = getComputedStyle(grid).gridTemplateColumns.split(' ').filter(Boolean).length
      return {
        w: width,
        cols,
        // Only the PINNED tiles matter — empty tracks are invisible.
        x: [...grid.querySelectorAll('.os-fav-tile')].map((el) => Math.round(el.getBoundingClientRect().x * 100) / 100),
      }
    }, w))
  }
  // The topmost column detent for this pin count, straight from the rule in
  // railResize.ts: 84·n + 8·(n-1) + 24 margin + 10 chrome, n = min(pins, 4).
  const top = pins === 0 ? 88 : Math.min(pins, 4) * 84 + (Math.min(pins, 4) - 1) * 8 + 24 + 10
  const free = rows.filter((r) => r.w > top)
  const rigid = rows.filter((r) => r.w <= top)
  const xsOver = (band, i) => [...new Set(band.map((r) => r.x[i]).filter((v) => v !== undefined))]
  const freeMoves = []
  const rigidMoves = []
  for (let i = 0; i < pins; i += 1) {
    const f = xsOver(free, i)
    if (f.length > 1) freeMoves.push({ tile: i + 1, distinctX: f })
    const g = xsOver(rigid, i)
    if (g.length > 1) rigidMoves.push({ tile: i + 1, distinctX: g })
  }
  byPins.push({
    pins,
    topColumnDetent: top,
    freeBand: [top + 1, 420],
    rigidBand: [88, top],
    freeCols: [...new Set(free.map((r) => r.cols))],
    // THE ASSERTION: no pinned tile moves anywhere in its own free band.
    freeTileMoves: freeMoves,
    // The reason the guard exists, reported as evidence rather than an
    // assertion: at 2+ pins some pinned tile DOES move inside the rigid band.
    rigidTileMoves: rigidMoves,
  })
}

/**
 * #1730 — the column progression must be MEASURED, and it must REACH the
 * documented shape.
 *
 * `cols` used to be measured, printed, and never entered a failure predicate.
 * The only predicate was `violations`, built from `multi = sweep.filter(cols >= 2)`:
 * a grid collapsed to a single column makes `multi` EMPTY, so `violations` is
 * empty, the invariant "tiles 1 and 2 never move sideways" is trivially
 * satisfied, and the PASS line below still hardcoded `1->2->3->4` no matter what
 * the sweep found. Deleting `grid-template-columns` from the base
 * `.os-fav-grid` rule reproduced it exactly -- 1 col at all six detents, zero
 * violations, green -- while the rail could no longer seat 2, 3 or 4 pinned
 * agents. The rail's whole reason for existing is that progression.
 *
 * So `cols` gates now, and it fails CLOSED: if the sweep cannot read a column
 * count, or seats fewer agents as the rail widens, or never reaches the
 * documented top shape, this exits non-zero rather than reporting an invariant
 * it never exercised.
 */
const EXPECTED_TOP_COLUMNS = 4 // railWidthForColumns(4)=394 fits MAX_RAIL_WIDTH=420

/** The distinct column counts the sweep passed through, in order. */
const progression = []
for (const r of sweep) {
  const last = progression[progression.length - 1]
  if (last && last.cols === r.cols) continue
  progression.push({ railWidth: r.railWidth, cols: r.cols })
}
const progressionCounts = progression.map((p) => p.cols)
const progressionPath = progressionCounts.join('->')

const unmeasurable = sweep.filter((r) => !(r.cols >= 1))
const regressions = sweep.filter((r, i) => i > 0 && r.cols < sweep[i - 1].cols)
const widest = sweep[sweep.length - 1]

const progressionProblems = []
if (!sweep.length) {
  progressionProblems.push('the sweep measured no rail widths at all, so nothing below is evidence')
} else if (unmeasurable.length) {
  progressionProblems.push(
    `${unmeasurable.length} width(s) reported no measurable column count (cols < 1), ` +
      `first at ${unmeasurable[0].railWidth}px -- grid-template-columns could not be read, ` +
      `so the tile-x invariant below is vacuous`,
  )
}
if (regressions.length) {
  progressionProblems.push(
    `a WIDER rail seated FEWER agents at ${regressions.length} width(s), ` +
      `first at ${regressions[0].railWidth}px (${regressions[0 - 1].cols} -> ${regressions[0].cols})`,
  )
}
if (widest && widest.cols < EXPECTED_TOP_COLUMNS) {
  progressionProblems.push(
    `the widest rail (${widest.railWidth}px) seats only ${widest.cols} column(s); the ` +
      `documented shape is ${EXPECTED_TOP_COLUMNS} (railWidthForColumns(4)=394 fits ` +
      `inside MAX_RAIL_WIDTH=420). A grid that can never seat 2, 3 or 4 pinned ` +
      `agents satisfies the tile-x invariant trivially and pins nothing.`,
  )
}

const report = {
  tiles: TILES,
  detents: byDetent,
  just: sweep[0]?.justifyContent,
  progression: progressionPath,
  progressionProblems,
  violations,
  byPins,
  shots,
}
await browser.close()

if (jsonOut) {
  console.log(JSON.stringify(report, null, 2))
} else {
  console.log(`justify-content: ${report.just}`)
  for (const d of byDetent) console.log(`  rail ${d.railWidth}px -> ${d.cols} cols, tile x: ${JSON.stringify(d.tileX)}`)
  if (progressionProblems.length) {
    console.log(`\nFAIL — the ${progressionCounts.length}-stop column progression is not the documented shape:`)
    for (const p of progressionProblems) console.log(`  ${p}`)
    console.log(`  measured progression: ${progressionPath}`)
  }
  if (violations.length) {
    console.log(`\nFAIL — ${violations.length} tile(s) move horizontally:`)
    for (const v of violations) console.log(`  tile ${v.tile}: distinct x = ${JSON.stringify(v.distinctX)}`)
  }
  if (!progressionProblems.length && !violations.length) {
    // The measured counts, never a hardcoded claim: the progression is the
    // evidence, and printing a constant here is what made the old gate lie.
    console.log(
      `\nPASS — measured progression ${progressionPath} across ` +
        `${progression.length} stop(s); tiles 1 and 2 hold their x across every transition`,
    )
  }

  console.log(`\n${'='.repeat(96)}`)
  console.log('#1683 PER-PIN-COUNT AUDIT — is free-tracking above the topmost detent wobble-free?')
  console.log('='.repeat(96))
  console.log(
    'pins'.padEnd(6) +
    'topDetent'.padEnd(11) +
    'free band'.padEnd(14) +
    'cols there'.padEnd(12) +
    'tiles moving in FREE band',
  )
  console.log('-'.repeat(96))
  for (const r of byPins) {
    console.log(
      String(r.pins).padEnd(6) +
        String(r.topColumnDetent).padEnd(11) +
        `${r.freeBand[0]}..${r.freeBand[1]}`.padEnd(14) +
        JSON.stringify(r.freeCols).padEnd(12) +
        (r.freeTileMoves.length
          ? `FAIL — ${r.freeTileMoves.map((m) => `tile ${m.tile} at ${JSON.stringify(m.distinctX)}`).join('; ')}`
          : 'none (all pinned tiles hold their x)'),
    )
  }
  console.log(
    '\n' +
    'rigid band (where RAIL_DETENT_ALWAYS applies), same sweep — the wobble #1262 names:',
  )
  for (const r of byPins) {
    if (!r.rigidTileMoves.length) continue
    console.log(
      `  ${r.pins} pin(s), ${r.rigidBand[0]}..${r.rigidBand[1]}px: ` +
        r.rigidTileMoves.map((m) => `tile ${m.tile} moves across ${JSON.stringify(m.distinctX)}`).join('; '),
    )
  }
}

const freeBandWobble = byPins.filter((r) => r.freeTileMoves.length)
if (freeBandWobble.length) {
  console.log(
    `\nFAIL — free-tracking would wobble for ${freeBandWobble.length} pin count(s): ` +
      freeBandWobble.map((r) => `${r.pins} pin(s)`).join(', '),
  )
}
if (SHOTS) console.log(`shots: ${shots.join(', ')}`)
// #1730: `progressionProblems` joins the exit predicate. Before, the only
// inputs were `violations` and `freeBandWobble`, both of which are empty for a
// grid that can never seat two agents -- so the gate was green while the rail
// could not do its job.
process.exit(violations.length || freeBandWobble.length || progressionProblems.length ? 1 : 0)
