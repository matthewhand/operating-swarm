#!/usr/bin/env node
/**
 * #1704 — before/after visual proof + the cross-build height comparison.
 *
 * Two bundles in hand:
 *   BEFORE  the parent of the commit that moved the folder affordance into the
 *           action cluster, where "Select folder" is a TEXT row inside the
 *           stacked label column;
 *   AFTER   this branch, where it is a right-aligned icon beside the pencil.
 *
 * Both are measured on the SAME harness path with the SAME props, so the only
 * difference in the numbers is the affordance. That is the ticket's own
 * criterion — "pill height with folder+pencil icons ≤ height without the old
 * text row" — and it is not measurable inside one build, because the text row
 * no longer exists in one of them.
 *
 * Screenshots: dark, fonts loaded, and the path in-frame (the proof page paints
 * `window.location.href` in its own address bar, so each PNG is self-identifying
 * with no secrets).
 *
 * Usage, from the repo root, with both previews already serving:
 *   node scripts/capture_1704_folder_pill.mjs
 * with
 *   PLAYWRIGHT_BASE_URL        (after,  default http://127.0.0.1:8001)
 *   PLAYWRIGHT_BASE_URL_BEFORE (before, default http://127.0.0.1:8002)
 *
 * Exits non-zero when the after build is not shorter, so a regression fails the
 * capture rather than producing a reassuring screenshot.
 */
import { mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '../webui/frontend/node_modules/playwright/index.mjs'

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const AFTER = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8001'
const BEFORE = process.env.PLAYWRIGHT_BASE_URL_BEFORE || 'http://127.0.0.1:8002'
const OUT_DIR = path.join(REPO, 'docs', 'screenshots', '1704')
const CHROME = process.env.CHROME_PATH || 'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe'
const UNSET = '/__proof__/folder-pill-1704?theme=dark&folder=unset'
const BOUND = '/__proof__/folder-pill-1704?theme=dark&folder=bound'

/**
 * Pill height with the affordance REVEALED, in a real renderer.
 *
 * Hover is applied for the before build too: the text row is `opacity-0` until
 * the pill is hovered, so measuring it at rest would flatter the old build and
 * make the comparison meaningless. The height it occupies is the same either
 * way (opacity never reflows) — that is the whole complaint, and here it is the
 * thing being proven.
 */
async function measureRevealed(page, base, url) {
  await page.goto(`${base}${url}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('[data-testid="selected-agent-header"]')
  await page.evaluate(() => document.fonts?.ready)
  await page.hover('[data-testid="selected-agent-header"]')
  await page.waitForTimeout(300)
  return page.evaluate(() => {
    const pill = document.querySelector('[data-testid="selected-agent-header"]')
    const column = pill.querySelector('.os-navbar-identity-text')
    const actions = document.querySelector('.os-agent-pill__actions')
    const folder = document.querySelector('[data-testid="os-navbar-workspace-subtitle-unset"]')
    return {
      pillH: pill.getBoundingClientRect().height,
      labelRows: column ? column.children.length : null,
      hasActionCluster: !!actions,
      folderInColumn: !!folder?.closest('.os-navbar-identity-text'),
      folderText: (folder?.textContent || '').trim(),
    }
  })
}

async function shot(page, name) {
  await page.evaluate(async () => {
    if (document.fonts?.ready) await document.fonts.ready
  })
  const dest = path.join(OUT_DIR, name)
  await page.screenshot({ path: dest, fullPage: false })
  console.log('wrote', dest)
  return dest
}

async function main() {
  mkdirSync(OUT_DIR, { recursive: true })
  const browser = await chromium.launch({ headless: true, executablePath: CHROME })
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    colorScheme: 'dark',
  })
  const page = await context.newPage()

  // --- BEFORE: the text row -----------------------------------------------------
  await page.goto(`${BEFORE}${UNSET}`, { waitUntil: 'networkidle' })
  await page.getByTestId('selected-agent-header').waitFor({ state: 'visible' })
  await page.getByTestId('proof-url-1704').waitFor({ state: 'visible' })
  const before = await measureRevealed(page, BEFORE, UNSET)
  await page.hover('[data-testid="selected-agent-header"]')
  await page.waitForTimeout(300)
  await shot(page, '#1704-before-folder-text-row-dark.png')

  // --- AFTER: the icon, revealed -------------------------------------------------
  await page.goto(`${AFTER}${UNSET}`, { waitUntil: 'networkidle' })
  await page.getByTestId('selected-agent-header').waitFor({ state: 'visible' })
  await page.getByTestId('proof-url-1704').waitFor({ state: 'visible' })
  const after = await measureRevealed(page, AFTER, UNSET)
  await page.hover('[data-testid="selected-agent-header"]')
  await page.waitForTimeout(300)
  await shot(page, '#1704-after-folder-icon-revealed-dark.png')

  // --- AFTER at rest: same pill, no reveal ---------------------------------------
  await page.goto(`${AFTER}${UNSET}`, { waitUntil: 'networkidle' })
  await page.getByTestId('selected-agent-header').waitFor({ state: 'visible' })
  await page.mouse.move(0, 0)
  await page.waitForTimeout(300)
  const atRest = await page.evaluate(
    () => document.querySelector('[data-testid="selected-agent-header"]').getBoundingClientRect().height,
  )
  await shot(page, '#1704-after-folder-icon-at-rest-dark.png')

  // --- the control: a bound folder is a bottom label, not an icon ---------------
  await page.goto(`${AFTER}${BOUND}`, { waitUntil: 'networkidle' })
  await page.getByTestId('selected-agent-header').waitFor({ state: 'visible' })
  await page.getByTestId('proof-url-1704').waitFor({ state: 'visible' })
  const bound = await measureRevealed(page, AFTER, BOUND)
  await shot(page, '#1704-after-folder-bound-dark.png')

  await browser.close()

  const rows = [
    ['before (text row in the label column)', before],
    ['after (icon in the action cluster)', after],
  ]
  console.log('')
  console.log('pill height with the affordance revealed:')
  for (const [label, m] of rows) {
    console.log(`  ${label.padEnd(42)} ${m.pillH.toFixed(2)}px · ${m.labelRows} label row(s)`)
  }
  console.log(`  ${'after at rest (nothing revealed)'.padEnd(42)} ${atRest.toFixed(2)}px`)

  const failures = []
  if (after.pillH > before.pillH + 0.5) {
    failures.push(
      `the icon pill is TALLER than the text row it replaced: ${after.pillH.toFixed(2)}px vs ${before.pillH.toFixed(2)}px`,
    )
  }
  if (Math.abs(atRest - after.pillH) > 0.5) {
    failures.push(
      `revealing the affordance changed the pill height: ${atRest.toFixed(2)}px at rest vs ${after.pillH.toFixed(2)}px revealed`,
    )
  }
  if (!after.hasActionCluster) failures.push('the after build has no .os-agent-pill__actions cluster')
  if (after.folderInColumn) failures.push('the after build still nests the folder control in the label column')
  if (!before.folderText.toLowerCase().includes('select folder')) {
    failures.push(`the before build did not render the "Select folder" text row (got ${JSON.stringify(before.folderText)})`)
  }
  if (bound.folderText) {
    failures.push('a bound folder still offers the unset affordance')
  }

  if (failures.length) {
    console.error('')
    console.error('#1704 proof FAILED:')
    for (const line of failures) console.error(`  - ${line}`)
    process.exit(1)
  }
  console.log('')
  console.log(
    `#1704 OK — ${after.pillH.toFixed(2)}px with the icon vs ${before.pillH.toFixed(2)}px with the text row ` +
      `(${(before.pillH - after.pillH).toFixed(2)}px shorter)`,
  )
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
