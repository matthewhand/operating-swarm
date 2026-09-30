/**
 * Capture #1397 pack/import/status screenshots with the repo path in-frame.
 * Run against the demo preview (VITE_DEMO_MODE) so no tokens exist.
 */
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { chromium } from 'playwright'

const OUT_DIR = process.argv[2] || join(process.cwd(), '../../docs/screenshots/req1397-plugins-pack')
const BASE = process.env.CAPTURE_BASE || 'http://127.0.0.1:4177/'
mkdirSync(OUT_DIR, { recursive: true })

function banner(page, relPath) {
  return page.evaluate((text) => {
    document.querySelectorAll('[data-capture-path]').forEach((el) => el.remove())
    const el = document.createElement('div')
    el.dataset.capturePath = '1'
    el.textContent = text
    el.style.cssText = [
      'position:fixed',
      'top:0',
      'left:0',
      'right:0',
      'z-index:2147483647',
      'background:#111827',
      'color:#f9fafb',
      'font:13px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace',
      'padding:8px 12px',
      'border-bottom:2px solid #38bdf8',
    ].join(';')
    document.body.appendChild(el)
    document.body.style.paddingTop = '36px'
  }, relPath)
}

async function shot(page, name) {
  const rel = `docs/screenshots/req1397-plugins-pack/${name}`
  await banner(page, rel)
  await page.waitForTimeout(150)
  const dest = join(OUT_DIR, name)
  await page.screenshot({ path: dest, fullPage: false })
  console.log('wrote', dest)
}

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })
page.setDefaultTimeout(20000)
await page.goto(BASE, { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2500)

const pluginsBtn = page.getByTestId('os-plugins-button')
await pluginsBtn.scrollIntoViewIfNeeded()
await pluginsBtn.click()
await page.waitForSelector('[data-testid="os-plugins-popup"]')
await page.getByRole('tab', { name: 'Pack' }).click()
await page.waitForSelector('[data-testid="os-plugin-pack-pane"]')
await page.waitForTimeout(600)
await shot(page, '1-pack-status-enabled-missing.png')

const importBox = page.getByRole('textbox', { name: 'Import pack' })
await importBox.fill('web_search\nunknown-plugin-id')
await page.waitForTimeout(200)
await shot(page, '2-pack-import-ids.png')

await page.keyboard.press('Escape')
await page.waitForTimeout(400)
await page.evaluate(() => {
  window.dispatchEvent(new CustomEvent('swarm:open-settings', { detail: { section: 'plugins' } }))
})
await page.waitForSelector('[data-testid="os-plugins-settings"]')
await page.waitForTimeout(700)
await shot(page, '3-settings-plugin-pack.png')

await browser.close()
console.log('saved:', OUT_DIR)
