#!/usr/bin/env node
/**
 * #1709 dark path-in-frame before/after: add chat with existing agent.
 * Stubs POST /sessions so rate-limits cannot blank the after state.
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '../webui/frontend/node_modules/playwright/index.mjs'

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const BASE = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8002'
const OUT_DIR = process.env.CAPTURE_OUT || path.join(REPO, 'docs', 'screenshots', '1709')
const CHROME = process.env.CHROME_PATH || 'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe'
const FRESH_ID = 'proof-1709-fresh-support'

async function installUrlChrome(page, href, label) {
  await page.evaluate(({ url, label }) => {
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
        <span style="margin-left:8px;opacity:.85">OpenRig · #1709 ${label}</span>
      </div>
      <div style="display:flex;align-items:center;gap:8px;background:#111;border:1px solid #3f3f46;border-radius:999px;padding:6px 12px">
        <span aria-hidden="true">🔒</span>
        <span data-testid="os-proof-capture-url">${url}</span>
      </div>`
    document.body.style.paddingTop = '68px'
  }, { url: href, label })
}

async function shot(page, name) {
  await page.evaluate(async () => { if (document.fonts?.ready) await document.fonts.ready })
  const dest = path.join(OUT_DIR, name)
  await page.screenshot({ path: dest, fullPage: false })
  console.log('wrote', dest)
  return dest
}

async function main() {
  mkdirSync(OUT_DIR, { recursive: true })
  const browser = await chromium.launch({ headless: true, executablePath: CHROME })
  const context = await browser.newContext({
    viewport: { width: 1400, height: 900 },
    colorScheme: 'dark',
  })
  await context.addInitScript(() => {
    try {
      localStorage.setItem('swarm_theme', 'dark')
      localStorage.setItem('swarm_rail_width', '302')
    } catch {}
  })
  const page = await context.newPage()

  // Stub session create so 429 cannot blank the after shot. Live SPA + PR JS still drive UI.
  await page.route('**/v1/agents/*/sessions/**', async (route) => {
    const req = route.request()
    const url = req.url()
    const method = req.method().toUpperCase()
    const m = url.match(/\/v1\/agents\/([^/]+)\/sessions/)
    const agentId = m ? decodeURIComponent(m[1]) : 'support'
    if (method === 'POST') {
      const body = {
        object: 'agent_session',
        id: FRESH_ID,
        conversation_id: FRESH_ID,
        agent_id: agentId,
        title: 'New session',
        snippet: '',
        created_at: '2026-09-29T09:50:00.000Z',
        updated_at: '2026-09-29T09:50:00.000Z',
        labels: [],
        cli_session_id: null,
        empty: true,
        status: 'finished',
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    }
    if (method === 'GET') {
      const body = {
        object: 'agent_session_list',
        agent_id: agentId,
        sessions: [{
          object: 'agent_session',
          id: FRESH_ID,
          conversation_id: FRESH_ID,
          agent_id: agentId,
          title: 'New session',
          snippet: '',
          created_at: '2026-09-29T09:50:00.000Z',
          updated_at: '2026-09-29T09:50:00.000Z',
          labels: [],
          cli_session_id: null,
          empty: true,
          status: 'finished',
        }],
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    }
    return route.continue()
  })

  // Soft-stub noisy endpoints that 429 in dogfood without affecting the flow
  await page.route('**/v1/agents/*/settings/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }))
  await page.route('**/v1/agents/*/profile/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }))
  await page.route('**/v1/agents/*/skills/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: [] }) }))

  const beforePath = '/chat?blueprint=codey&proof=1709-before-prior-selection'
  const beforeUrl = `${BASE}${beforePath}`
  await page.goto(beforeUrl, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'))
  await page.waitForSelector('.os-agent-sidebar, [data-testid="add-bot-menu-trigger"]', { timeout: 30000 })
  await page.waitForTimeout(1200)

  await installUrlChrome(page, beforeUrl, 'before')
  await shot(page, '#1709-before-prior-selection-dark.png')

  // Remove chrome for interaction, then re-add after
  await page.evaluate(() => {
    document.getElementById('os-proof-capture-chrome')?.remove()
    document.body.style.paddingTop = ''
  })

  await page.getByTestId('add-bot-menu-trigger').click()
  await page.getByTestId('os-add-bot-menu').waitFor({ state: 'visible', timeout: 10000 })
  const pick = page.getByTestId('os-add-bot-menu-agent-support')
  await pick.waitFor({ state: 'visible', timeout: 10000 })
  await Promise.all([
    page.waitForURL(/blueprint=support/, { timeout: 15000 }).catch(() => null),
    pick.click(),
  ])
  await page.waitForTimeout(1500)
  await page.waitForLoadState('networkidle').catch(() => {})

  let afterHref = page.url()
  // Ensure proof query is visible in the chrome bar
  const chromeUrl = afterHref.includes('proof=')
    ? afterHref
    : `${afterHref}${afterHref.includes('?') ? '&' : '?'}proof=1709-after-new-chat-selected`
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'))
  await installUrlChrome(page, chromeUrl, 'after')
  await page.waitForTimeout(400)
  await shot(page, '#1709-after-new-chat-selected-dark.png')

  const meta = {
    beforeUrl,
    afterUrl: afterHref,
    chromeUrl,
    theme: await page.evaluate(() => document.documentElement.getAttribute('data-theme')),
    font: await page.evaluate(() => getComputedStyle(document.body).fontFamily),
    selectedHeader: await page.evaluate(() =>
      document.querySelector('[data-testid="selected-agent-header"]')?.textContent?.slice(0, 120) || null),
    activeRow: await page.evaluate(() => {
      const row = document.querySelector('.os-agent-row--active, [data-active="true"], .os-agent-row[aria-current="page"]')
      return row ? row.textContent?.slice(0, 120) : null
    }),
  }
  writeFileSync(path.join(OUT_DIR, '#1709-capture-meta.json'), JSON.stringify(meta, null, 2))
  console.log('meta', meta)

  if (!/support/i.test(afterHref) && !/support/i.test(meta.selectedHeader || '')) {
    console.error('FAIL: after state did not switch to support / new session')
    process.exit(1)
  }
  await browser.close()
}

main().catch((e) => { console.error(e); process.exit(1) })
