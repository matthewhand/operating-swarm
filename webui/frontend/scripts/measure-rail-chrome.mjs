// Real-renderer geometry check for the rail's top chrome.
//
// jsdom has no layout engine, so it cannot answer "does the collapse control
// end up below the Add button". This renders the rail's chrome DOM against the
// BUILT stylesheet (dist/assets/*.css -- the same bytes the browser serves) at
// each detent width and reports the actual box geometry.
//
// The DOM below is copied from AgentSidebar.tsx (the search row, the hoisted
// avatar-only expand control, the pinned-tile grid). Keep them in step: if the
// component's classNames change, update this file or the measurement is fiction.
//
// Run: `npm run build` first (this harness reads the BUILT stylesheet), then
// `node scripts/measure-rail-chrome.mjs`.
// The Chromium binary is resolved rather than hardcoded — see
// `scripts/chromiumBinary.mjs` for why a gate that cannot launch is worse than
// no gate at all.
import { chromium } from 'playwright'
import { readFileSync, readdirSync } from 'node:fs'
import { CHROMIUM_ARGS, resolveChromium } from './chromiumBinary.mjs'

// #1683: the ladder now runs to FOUR columns — `railWidthForColumns(4)` = 394
// fits inside MAX_RAIL_WIDTH (420), so the 4-column width is a real detent and
// the rail's chrome has to survive it. Added to the sweep below; the harness is
// the gate for "the search row's controls still lead the chrome at every width
// the drag can actually stop on".
const DETENTS = [
  { name: 'ultra-compact (88)', width: 88 },
  { name: '1 wide (118)', width: 118 },
  { name: '2 wide (210)', width: 210 },
  { name: '3 wide (302)', width: 302 },
  { name: '4 wide (394)', width: 394 },
  { name: 'max (420)', width: 420 },
]

// The gap the user reported: widths above the avatar-only line but below the
// one-column detent. The snap physics settle at 88 or 118, so these are only
// reachable mid-drag -- but a resize observer or a restored legacy value can
// land here too.
const DEAD_ZONE = [89, 96, 100, 110, 117]

const builtCss = readdirSync('dist/assets')
  .filter((f) => f.endsWith('.css'))
  .map((f) => readFileSync(`dist/assets/${f}`, 'utf8'))
  .join('\n')

// The rail's collapse control, verbatim from SidepaneConceal.tsx's
// `SidebarConcealButton` — the `h-9 w-9` is what makes it 2.25rem, and the
// `os-rail-conceal` hook is what the 1-col search row reorders. Measuring a
// stand-in `btn-xs` here would understate the row by 2px per control, which is
// exactly the budget #1711 spends.
const concealBtn = (extra) =>
  `<button type="button" class="btn btn-ghost btn-sm btn-square min-h-9 min-w-9 h-9 w-9 text-base-content ${extra}" aria-label="Collapse sidebar">${'<svg class="h-4 w-4" viewBox="0 0 24 24"><path d="M15 6l-6 6 6 6" stroke="currentColor" stroke-width="2" fill="none"/></svg>'}</button>`

const searchRow = (withConceal) => `
  <div class="os-rail-search-row flex items-center gap-1.5 px-3 pb-2 pt-3">
    <button type="button" class="os-rail-search min-w-0 flex-1 cursor-pointer" data-probe="search">
      <svg class="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24"><path d="M11 4a7 7 0 105.2 11.6L21 20" stroke="currentColor" stroke-width="2" fill="none"/></svg>
      <span class="os-rail-search__input os-rail-search__placeholder">Search</span>
      <kbd class="os-rail-search__kbd kbd kbd-xs">/</kbd>
    </button>
    <button type="button" class="os-search-add-btn" data-probe="add" aria-label="Add agent">
      <svg class="h-4 w-4" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2"/></svg>
    </button>
    ${withConceal ? concealBtn('os-rail-conceal').replace('<button', '<button data-probe="conceal"') : ''}
  </div>`

const shell = (width, avatarOnly) => `
<div class="pane" data-width="${width}">
  <aside class="os-agent-sidebar ${avatarOnly ? 'os-agent-sidebar--avatar-only' : ''}" style="width:${width}px" data-avatar-only="${avatarOnly}">
    ${avatarOnly ? `<div class="os-rail-top-toggle" data-probe="top-toggle" data-rail-side="left">${concealBtn('').replace('Collapse sidebar', 'Expand sidebar').replace('<button', '<button data-probe="expand"')}</div>` : ''}
    ${searchRow(!avatarOnly)}
    <div class="os-fav-grid" data-probe="fav-grid">
      ${[0, 1, 2, 3, 4, 5, 6, 7].map(() => '<div class="os-fav-tile"></div>').join('')}
    </div>
  </aside>
</div>`

const browser = await chromium.launch({
  executablePath: resolveChromium(),
  args: CHROMIUM_ARGS,
})
const page = await browser.newPage({ viewport: { width: 1400, height: 700 } })
await page.setContent(
  `<!doctype html><html data-theme="dark"><head><meta charset="utf-8"><style>
   ${builtCss}
   body{margin:0;font-family:ui-sans-serif,system-ui,sans-serif}
   .pane{width:var(--w)}
  </style></head><body><div id="host"></div></body></html>`,
  { waitUntil: 'load' },
)

async function measure(width) {
  const avatarOnly = width <= 88
  await page.evaluate(
    ([w, html]) => {
      document.getElementById('host').innerHTML = html
      document.querySelector('.pane').style.setProperty('--w', w + 'px')
    },
    [width, shell(width, avatarOnly)],
  )
  return page.evaluate(
    ([wantAvatarOnly, wantWidth]) => {
      const ONE_COL = 118
      const pane = document.querySelector('.pane')
      const paneW = pane.getBoundingClientRect().width
      const row = document.querySelector('.os-rail-search-row')
      const rowBox = row.getBoundingClientRect()
      const kids = [...row.children].map((c) => {
        const r = c.getBoundingClientRect()
        return {
          probe: c.dataset.probe || c.className.slice(0, 22),
          y: Math.round(r.y * 10) / 10,
          bottom: Math.round(r.bottom * 10) / 10,
          x: Math.round(r.x * 10) / 10,
          w: Math.round(r.width * 10) / 10,
          overflowsRight: Math.round((r.right - paneW) * 10) / 10,
        }
      })
      // A "band" is one horizontal strip of the row. Compare vertical
      // INTERVALS, not top edges: `items-center` gives children of different
      // heights different y for the same line, so a 6px y delta is alignment,
      // not a wrap. Two controls share a band when their vertical extents
      // overlap.
      const bands = []
      for (const k of kids) {
        const hit = bands.find((b) => k.y < b.bottom - 1 && k.bottom > b.y + 1)
        if (hit) {
          hit.y = Math.min(hit.y, k.y)
          hit.bottom = Math.max(hit.bottom, k.bottom)
          hit.members.push(k.probe)
        } else {
          bands.push({ y: k.y, bottom: k.bottom, members: [k.probe] })
        }
      }
      const stacked = bands.length > 1
      const byProbe = Object.fromEntries(kids.map((k) => [k.probe, k]))
      // #1711: the acceptance is that the collapse control is never a control
      // alone on a band — "alongside Search and +, or with Search alone when
      // they wrap", never a third circle under `+`. `+` wrapping away to a
      // band of its own IS blessed (the issue says so); the collapse control
      // is not, so the orphan gate below is scoped to it.
      const concealBand = byProbe.conceal && bands.find((b) => b.members.includes('conceal'))
      const sharesSearch =
        !byProbe.conceal || !byProbe.search || (concealBand?.members.includes('search') ?? false)
      const orphans = bands
        .filter((b) => b.members.length < 2 && b.members.includes('conceal'))
        .map((b) => b.members[0])
      // The 1-col detent itself must be a SINGLE band: at 118px the three
      // 2.25rem controls fit one line, so the header matches the wide detents'
      // 56px chrome strip instead of growing into a second row.
      const singleBandAtOneCol = wantWidth === ONE_COL ? bands.length === 1 : null
      return {
        paneW,
        avatarOnly: wantAvatarOnly,
        rowH: Math.round(rowBox.height * 10) / 10,
        rowRightOverflow: Math.round((rowBox.right - paneW) * 10) / 10,
        kids,
        bands: bands.map((b) => `${b.members.join(' + ')} @y${b.y}`),
        stacked,
        sharesSearch,
        orphans,
        singleBandAtOneCol,
      }
    },
    [avatarOnly, width],
  )
}

/** Every way this measurement can fail, as data rather than as prose. */
function failuresAt(width, m) {
  const bad = []
  if (m.rowRightOverflow > 0.5) bad.push('row overflows the rail')
  // At ultra-compact the collapse control is hoisted out of the row into
  // `.os-rail-top-toggle`, so the row legitimately carries two controls.
  if (m.kids.some((k) => k.probe === 'conceal')) {
    if (!m.sharesSearch) bad.push('collapse is NOT on the search band')
    if (m.orphans.length) bad.push(`collapse orphaned: ${m.orphans.join(', ')}`)
    if (m.singleBandAtOneCol === false) bad.push('1-col detent is not a single band')
  }
  return bad
}

console.log('='.repeat(96))
console.log('RAIL TOP CHROME — real-renderer geometry (built CSS, Chrome)')
console.log('='.repeat(96))
console.log(
  '\n' + 'detent'.padEnd(24) + 'avatarOnly'.padEnd(12) + 'bands'.padEnd(34) + 'rowH'.padEnd(8) + 'overflowX'.padEnd(11) + 'verdict',
)
console.log('-'.repeat(96))

const failures = []
for (const d of DETENTS) {
  const m = await measure(d.width)
  const bad = failuresAt(d.width, m)
  if (bad.length) failures.push({ d: d.name, bad })
  console.log(
    d.name.padEnd(24) +
      String(m.avatarOnly).padEnd(12) +
      (m.stacked ? m.bands.join(' | ') : 'one band').padEnd(34) +
      String(m.rowH).padEnd(8) +
      String(m.rowRightOverflow).padEnd(11) +
      (bad.length ? 'FAIL: ' + bad.join('; ') : 'ok'),
  )
  for (const k of m.kids) {
    console.log(
      '    '.padEnd(24) +
        `${k.probe}: y=${k.y} x=${k.x} w=${k.w}` +
        (k.overflowsRight > 0.5 ? `  overflows rail by ${k.overflowsRight}px` : ''),
    )
  }
}

console.log('\n' + '='.repeat(96))
console.log('DEAD ZONE — 89..117px (above avatar-only line, below 1-col detent)')
console.log('='.repeat(96))
console.log('width'.padEnd(9) + 'avatarOnly'.padEnd(12) + 'bands'.padEnd(34) + 'rowH'.padEnd(8) + 'overflowX'.padEnd(11) + 'verdict')
for (const w of DEAD_ZONE) {
  const m = await measure(w)
  const bad = failuresAt(w, m)
  if (bad.length) failures.push({ d: `${w}px dead zone`, bad })
  console.log(
    String(w).padEnd(9) +
      String(w <= 88).padEnd(12) +
      (m.stacked ? m.bands.join(' | ') : 'one band').padEnd(34) +
      String(m.rowH).padEnd(8) +
      String(m.rowRightOverflow).padEnd(11) +
      (bad.length ? 'FAIL: ' + bad.join('; ') : 'ok'),
  )
}

await browser.close()
console.log(
  '\n' +
    (failures.length
      ? `FAIL (${failures.length}): ` + failures.map((f) => `${f.d} — ${f.bad.join('; ')}`).join(' | ')
      : 'PASS: the collapse control shares a band with Search at every width, no band is an orphan, and no row overflows the rail'),
)
process.exit(failures.length ? 1 : 0)
