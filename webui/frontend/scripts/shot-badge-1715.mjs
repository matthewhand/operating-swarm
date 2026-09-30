import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

const BASE = process.env.BASE || 'http://127.0.0.1:8015'
const OUT = resolve('../../docs/screenshots/dogfood-1715')
mkdirSync(OUT, { recursive: true })

const shots = [
  { name: 'unset-single-label-dark.png', path: '/__proof__/badge-pill-1715?theme=dark&folder=unset&role=off' },
  { name: 'bound-multiline-dark.png', path: '/__proof__/badge-pill-1715?theme=dark&folder=bound&role=off' },
]

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })
for (const s of shots) {
  const url = `${BASE}${s.path}`
  await page.goto(url, { waitUntil: 'networkidle' })
  await page.waitForSelector('[data-testid="selected-agent-header"]')
  await page.evaluate(() => document.fonts?.ready)
  // Ensure path-in-frame chrome is visible
  await page.waitForSelector('[data-testid="proof-url-1715"]')
  const dest = resolve(OUT, s.name)
  await page.screenshot({ path: dest, fullPage: false })
  console.log('SHOT', dest)
}
// Also run geometry measure if script works
await browser.close()
console.log('done')

