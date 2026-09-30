#!/usr/bin/env node
/**
 * #1711 dark path-in-frame before/after at 1-col rail width.
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '../webui/frontend/node_modules/playwright/index.mjs'

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const BASE = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8002'
const PHASE = (process.env.PROOF_PHASE || 'after').toLowerCase()
const OUT_DIR = process.env.CAPTURE_OUT || path.join(REPO, 'docs', 'screenshots', '1711')
const CHROME = process.env.CHROME_PATH || 'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe'
const PATH_Q = `/chat?blueprint=codey&proof=1711-${PHASE}-1col`
const PAGE_URL = `${BASE}${PATH_Q}`

async function installUrlChrome(page, href, phase) {
  await page.evaluate(({ url, phase }) => {
    let bar = document.getElementById('os-proof-capture-chrome')
    if (!bar) {
      bar = document.createElement('div')
      bar.id = 'os-proof-capture-chrome'
      bar.setAttribute('data-testid', 'os-proof-capture-chrome')
      document.body.prepend(bar)
    }
    bar.style.cssText = [
      'position:fixed', 'top:0', 'left:0', 'right:0', 'z-index:2147483647',
      'display:flex', 'flex-direction:column', 'gap:6px',
      'padding:8px 12px 10px', 'background:#1f1f1f', 'color:#f4f4f5',
      'font:13px/1.3 ui-sans-serif,system-ui,Segoe UI,sans-serif',
      'border-bottom:1px solid #3f3f46', 'box-shadow:0 8px 20px rgba(0,0,0,.35)',
    ].join(';')
    bar.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px">
        <span style="width:10px;height:10px;border-radius:99px;background:#f87171"></span>
        <span style="width:10px;height:10px;border-radius:99px;background:#fbbf24"></span>
        <span style="width:10px;height:10px;border-radius:99px;background:#34d399"></span>
        <span style="margin-left:8px;opacity:.85">OpenRig · #1711 ${phase}</span>
      </div>
      <div style="display:flex;align-items:center;gap:8px;background:#111;border:1px solid #3f3f46;border-radius:999px;padding:6px 12px">
        <span aria-hidden="true">🔒</span>
        <span data-testid="os-proof-capture-url">${url}</span>
      </div>`
    document.body.style.paddingTop = '68px'
  }, { url: href, phase })
}

async function main() {
  mkdirSync(OUT_DIR, { recursive: true })
  const browser = await chromium.launch({ headless: true, executablePath: CHROME })
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    colorScheme: 'dark',
  })
  await context.addInitScript(() => {
    try {
      localStorage.setItem('swarm_theme', 'dark')
      localStorage.setItem('swarm_rail_width', '118')
    } catch {}
  })
  const page = await context.newPage()

  await page.goto(PAGE_URL, { waitUntil: 'networkidle', timeout: 60000 })
  await page.evaluate(() => {
    localStorage.setItem('swarm_theme', 'dark')
    localStorage.setItem('swarm_rail_width', '118')
    document.documentElement.setAttribute('data-theme', 'dark')
    document.querySelectorAll('[data-theme]').forEach((el) => el.setAttribute('data-theme', 'dark'))
  })
  await page.goto(PAGE_URL, { waitUntil: 'networkidle', timeout: 60000 })
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'))

  await page.waitForSelector('.os-agent-sidebar, [data-testid="sidebar-conceal"], .os-rail-search-row', { timeout: 30000 })
  await page.waitForTimeout(1000)
  await page.evaluate(async () => { if (document.fonts?.ready) await document.fonts.ready })

  const geo = await page.evaluate(() => {
    const row = document.querySelector('.os-rail-search-row')
    const search = document.querySelector('.os-rail-search')
    const add = document.querySelector('[data-testid="add-bot-menu-trigger"], .os-search-add-btn')
    const conceal = document.querySelector('[data-testid="sidebar-conceal"], .os-rail-conceal')
    const aside = document.querySelector('.os-agent-sidebar')
    const box = (el) => {
      if (!el) return null
      const r = el.getBoundingClientRect()
      return { x: +r.x.toFixed(1), y: +r.y.toFixed(1), w: +r.width.toFixed(1), h: +r.height.toFixed(1) }
    }
    return {
      asideW: aside ? +aside.getBoundingClientRect().width.toFixed(1) : null,
      row: box(row),
      search: box(search),
      add: box(add),
      conceal: box(conceal),
      theme: document.documentElement.getAttribute('data-theme'),
      font: getComputedStyle(document.body).fontFamily,
    }
  })
  console.log('geometry', JSON.stringify(geo, null, 2))
  writeFileSync(path.join(OUT_DIR, `#1711-${PHASE}-geometry.json`), JSON.stringify(geo, null, 2))

  await installUrlChrome(page, PAGE_URL, PHASE)
  await page.waitForSelector('[data-testid="os-proof-capture-url"]')
  await page.waitForTimeout(200)

  const name = PHASE === 'before'
    ? '#1711-before-collapse-under-plus-dark.png'
    : '#1711-after-collapse-with-search-plus-dark.png'
  const dest = path.join(OUT_DIR, name)
  await page.screenshot({ path: dest, fullPage: false })
  console.log('wrote', dest)
  await browser.close()
}

main().catch((e) => { console.error(e); process.exit(1) })
