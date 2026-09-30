#!/usr/bin/env node
/**
 * #1395 unique product screenshots (export select + post-import fill-ins).
 *
 * Hermetic Playwright capture of the routines pack pane. Injects identifying
 * chrome with the issue id + route. No secrets. No live LLM.
 *
 * Usage (from repo root, with Vite already serving the SPA):
 *   PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 node scripts/capture_1395_routines_pack.mjs
 */
import { copyFileSync, mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '../webui/frontend/node_modules/playwright/index.mjs'

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const BASE = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:3000'
const OUT_DIR = path.join(REPO, 'docs', 'screenshots', '1395')
const ARTIFACT_DIR = process.env.ARTIFACTS_DIR || '/opt/cursor/artifacts'

const SHIP_NOTES = {
  id: 'r-notes',
  name: 'Ship notes',
  instruction: 'Summarize the merge.',
  active: true,
  trigger: {
    kind: 'github_pr_merged',
    owner_repo: 'acme/widgets',
    event: 'merged',
    actor: 'anyone',
  },
  history: [],
  when_to_run: 'When a PR merges in acme/widgets…',
}

const NIGHTLY = {
  id: 'r-nightly',
  name: 'Nightly recap',
  instruction: 'Summarize the day.',
  active: true,
  trigger: { kind: 'interval', seconds: 86400 },
  history: [],
  when_to_run: 'Every 1 day…',
}

const PACK = {
  object: 'agent_routines_pack',
  kind: 'agent_routines_pack',
  schema: 1,
  agent_id: 'codey',
  fill_ins: [{ key: 'owner_repo', label: 'GitHub owner/repo', required: true }],
  routines: [
    {
      name: 'GitHub Issue Solver (Issue → PR)',
      instruction: 'Investigate the issue in {{owner_repo}}.',
      trigger: {
        kind: 'github_event',
        event_type: 'issues.opened',
        owner_repo: '{{owner_repo}}',
      },
    },
  ],
}

const IMPORTED = {
  object: 'agent_routines_pack_import',
  agent_id: 'codey',
  pending_enable: true,
  created_count: 1,
  skipped: [],
  fill_ins_applied: [],
  fill_ins_remaining: [{ key: 'owner_repo', label: 'GitHub owner/repo', required: true }],
  routines: [
    {
      id: 'r-imported',
      name: 'GitHub Issue Solver (Issue → PR)',
      instruction: 'Investigate the issue in {{owner_repo}}.',
      active: false,
      trigger: {
        kind: 'github_event',
        event_type: 'issues.opened',
        owner_repo: '{{owner_repo}}',
      },
      history: [],
    },
  ],
  pack: PACK,
}

const BLUEPRINTS = {
  object: 'list',
  data: [
    {
      id: 'codey',
      object: 'blueprint',
      name: 'Codey',
      description: 'Code assistant',
      tags: [],
      installed: true,
      compiled: true,
      rail: true,
      kind: 'api',
    },
  ],
}

function json(route, body, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function stubApis(page) {
  await page.addInitScript(() => {
    class MockWs {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3
      readyState = 0
      onopen = null
      onmessage = null
      onclose = null
      send() {}
      close() {
        this.readyState = 3
      }
      constructor() {
        queueMicrotask(() => {
          this.readyState = 1
          this.onopen?.(new Event('open'))
        })
      }
    }
    window.WebSocket = MockWs
  })

  const fulfill = async (route) => {
    const parsed = new URL(route.request().url())
    const pathname = parsed.pathname
    const method = route.request().method()
    if (pathname.includes('/routines/pack')) return json(route, PACK)
    if (pathname.includes('/routines/import')) return json(route, IMPORTED)
    if (pathname.includes('/routines') && method === 'GET') {
      return json(route, {
        object: 'routine_list',
        agent_id: 'codey',
        routines: [SHIP_NOTES, NIGHTLY],
      })
    }
    if (pathname.startsWith('/v1/blueprints')) return json(route, BLUEPRINTS)
    if (pathname.startsWith('/chat/thread') || pathname.startsWith('/chat/')) {
      return json(route, {
        agent_id: 'codey',
        conversation_id: 'conv-1395',
        messages: [],
      })
    }
    if (pathname.includes('/test-schedules/status')) {
      return json(route, { object: 'test_schedule_status', failure_count: 0, failures: [] })
    }
    if (pathname.includes('/sandbox-display')) {
      return json(route, { available: false, reason: 'no_active_sandbox' })
    }
    if (pathname.startsWith('/v1/cli-agents')) return json(route, { clis: [] })
    if (pathname === '/health' || pathname === '/health/') return json(route, { status: 'ok' })
    return json(route, { object: 'list', data: [] })
  }

  await page.route('**/v1/**', fulfill)
  await page.route('**/chat/thread**', fulfill)
  await page.route((url) => {
    const { pathname } = new URL(url)
    return pathname === '/health' || pathname === '/health/'
  }, fulfill)
}

async function injectChrome(page, label) {
  await page.evaluate((text) => {
    const id = 'os-1395-capture-chrome'
    let bar = document.getElementById(id)
    if (!bar) {
      bar = document.createElement('div')
      bar.id = id
      bar.setAttribute('data-testid', 'os-1395-capture-chrome')
      bar.style.cssText = [
        'position:sticky',
        'top:0',
        'z-index:2147483647',
        'display:flex',
        'align-items:center',
        'gap:12px',
        'padding:8px 14px',
        'font:13px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace',
        'color:#111',
        'background:#f4f1ea',
        'border-bottom:2px solid #c45c26',
      ].join(';')
      document.body.insertBefore(bar, document.body.firstChild)
    }
    bar.textContent = text
  }, label)
}

async function openPackPane(page) {
  await page.getByRole('button', { name: 'Computer control' }).click()
  await page.getByRole('dialog', { name: 'Computer control' }).waitFor({ state: 'visible' })
  const routinesTab = page.getByRole('tab', { name: 'Routines' })
  if (await routinesTab.isVisible()) {
    await routinesTab.click()
  }
  await page.getByTestId('computer-routines-pane').waitFor({ state: 'visible' })
  await page.getByTestId('routine-pack-open').click()
  await page.getByTestId('routine-pack-picker').waitFor({ state: 'visible' })
}

async function main() {
  mkdirSync(OUT_DIR, { recursive: true })
  mkdirSync(ARTIFACT_DIR, { recursive: true })

  const executablePath = process.env.CHROME_PATH || '/usr/bin/google-chrome-stable'
  const browser = await chromium.launch({
    headless: true,
    executablePath,
    args: ['--no-sandbox', '--disable-gpu'],
  })
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } })
  await stubApis(page)

  const shots = []

  await page.goto(`${BASE}/chat?blueprint=codey#1395-export-select`, {
    waitUntil: 'domcontentloaded',
  })
  page.on('pageerror', (error) => {
    console.error('pageerror', error.message)
  })
  page.on('console', (msg) => {
    if (msg.type() === 'error') console.error('console', msg.text())
  })
  try {
    await page.getByRole('textbox', { name: 'Chat message' }).waitFor({ timeout: 20_000 })
  } catch (err) {
    await page.screenshot({
      path: path.join(ARTIFACT_DIR, '1395-capture-debug.png'),
      fullPage: true,
    })
    console.error('body', await page.locator('body').innerHTML().catch(() => ''))
    throw err
  }
  await openPackPane(page)
  await page.getByTestId('routine-pack-select-r-notes').waitFor()
  await injectChrome(
    page,
    `#1395  ${BASE}/chat?blueprint=codey#1395-export-select  ·  export select · Ship notes + Nightly recap`,
  )
  const exportPath = path.join(OUT_DIR, '1395-export-select.png')
  await page.screenshot({ path: exportPath, fullPage: false })
  shots.push(exportPath)

  await page.evaluate(() => {
    history.replaceState(null, '', '/chat?blueprint=codey#1395-import-fill-ins')
  })
  await page.getByTestId('routine-pack-import-json').fill(JSON.stringify(PACK, null, 2))
  await page.getByTestId('routine-pack-import').click()
  await page.getByTestId('routine-pack-fill-ins').waitFor({ state: 'visible' })
  await page.getByTestId('routine-pack-fill-in-owner_repo').fill('acme/widgets')
  await page.getByTestId('routine-pack-fill-ins').scrollIntoViewIfNeeded()
  await injectChrome(
    page,
    `#1395  ${BASE}/chat?blueprint=codey#1395-import-fill-ins  ·  post-import fill-ins · pending enable`,
  )
  const importPath = path.join(OUT_DIR, '1395-import-fill-ins.png')
  await page.screenshot({ path: importPath, fullPage: false })
  shots.push(importPath)

  for (const src of shots) {
    copyFileSync(src, path.join(ARTIFACT_DIR, path.basename(src)))
  }

  await browser.close()
  console.log(JSON.stringify({ ok: true, shots }, null, 2))
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
