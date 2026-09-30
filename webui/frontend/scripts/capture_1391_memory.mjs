/**
 * #1391 visual proof — Memory panel + export wizard.
 *
 * Hermetic: Playwright stubs /v1 (no secrets). Captures the live SPA at
 * /chat?blueprint=codey with a visible URL chrome bar in-frame.
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '@playwright/test'

const BASE = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:3000'
const OUT_DIR = process.env.CAPTURE_OUT
  || resolve(fileURLToPath(new URL('../../..', import.meta.url)), 'docs/screenshots')
const ARTIFACT_DIR = process.env.CAPTURE_ARTIFACTS || '/opt/cursor/artifacts'
const PAGE_URL = `${BASE}/chat?blueprint=codey`

const MEMORIES = [
  {
    object: 'agent_memory',
    id: 'p1',
    agent_id: 'codey',
    kind: 'profile',
    tier: 'pack',
    title: 'Voice',
    body: 'Prefers short answers.',
    created_at: '2026-09-27T00:00:00.000Z',
  },
  {
    object: 'agent_memory',
    id: 'l1',
    agent_id: 'codey',
    kind: 'log',
    tier: 'pack',
    title: 'Weekly review',
    body: 'Shipped the rail polish.',
    created_at: '2026-09-26T00:00:00.000Z',
  },
  {
    object: 'agent_memory',
    id: 'e1',
    agent_id: 'codey',
    kind: 'episode',
    tier: 'local',
    title: 'Tuesday chat',
    body: 'Private Tuesday chat.',
    created_at: '2026-09-25T00:00:00.000Z',
  },
  {
    object: 'agent_memory',
    id: 'n1',
    agent_id: 'codey',
    kind: 'note',
    tier: 'local',
    title: 'Scratch',
    body: 'Do not pack this.',
    created_at: '2026-09-24T00:00:00.000Z',
  },
]

const CODEY = {
  id: 'codey',
  object: 'blueprint',
  name: 'Codey',
  description: 'Code assistant',
  abbreviation: null,
  required_mcp_servers: [],
  tags: [],
  installed: true,
  compiled: true,
  rail: true,
}

async function stubApis(page) {
  const json = (body, status = 200) =>
    route =>
      route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify(body),
      })

  // Last matching Playwright route wins — register the catch-all first.
  await page.route('**/v1/**', json({ object: 'list', data: [] }))
  await page.route('**/v1/agents/**/memories/**', async (route) => {
    const url = route.request().url()
    const method = route.request().method()
    if (method === 'GET' && !url.includes('/pack/') && !url.includes('/import/')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          object: 'agent_memory_list',
          agent_id: 'codey',
          memories: MEMORIES,
        }),
      })
    }
    if (method === 'GET' && url.includes('/pack/')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          object: 'agent_memory_pack',
          schema: 1,
          memories: [
            { kind: 'profile', title: 'Voice', body: 'Prefers short answers.' },
            { kind: 'log', title: 'Weekly review', body: 'Shipped the rail polish.' },
          ],
        }),
      })
    }
    return route.fulfill({ status: 204, body: '' })
  })

  await page.route('**/v1/blueprints**', json({ object: 'list', data: [CODEY] }))
  await page.route('**/v1/models**', json({ object: 'list', data: [] }))
  await page.route('**/v1/teams**', json({ object: 'list', data: [] }))
  await page.route('**/v1/skills**', json({ object: 'list', data: [] }))
  await page.route('**/v1/cli-agents**', json({ clis: [], native_consensus: false }))
  await page.route('**/v1/llm-profiles**', json({
    object: 'llm_profiles',
    profiles: [],
    default_llm_profile: '',
    default_is_auto: false,
    override_per_task: false,
    task_llm_profiles: {},
    auto_picks: {},
    warnings: [],
    routes: {},
    task_classes: [],
  }))
  await page.route('**/v1/image-gen**', json({ configured: false }))
  await page.route('**/v1/remotes**', json({ object: 'list', data: [] }))
  await page.route('**/v1/roles**', json({ object: 'list', data: [] }))
  await page.route('**/v1/team-rosters**', json({ object: 'list', data: [] }))
  await page.route('**/v1/agents/**/settings/**', json({
    new_chat_per_task: false,
    use_suggestions: false,
    folder: '',
  }))
  await page.route('**/chat/thread/**', json({
    agent_id: 'codey',
    conversation_id: 'conv-1391',
    messages: [],
  }))
  await page.route('**/health**', json({ status: 'ok' }))
}

async function installUrlChrome(page, url) {
  await page.evaluate((href) => {
    let bar = document.getElementById('os-1391-capture-chrome')
    if (!bar) {
      bar = document.createElement('div')
      bar.id = 'os-1391-capture-chrome'
      bar.setAttribute('data-testid', 'os-1391-capture-chrome')
      document.body.appendChild(bar)
    }
    bar.style.cssText = [
      'position:fixed',
      'top:0',
      'left:0',
      'right:0',
      'z-index:2147483647',
      'display:flex',
      'flex-direction:column',
      'gap:6px',
      'padding:8px 12px 10px',
      'background:#1f1f1f',
      'color:#f4f4f5',
      'font:13px/1.3 ui-sans-serif,system-ui,sans-serif',
      'border-bottom:1px solid #3f3f46',
      'box-shadow:0 8px 20px rgba(0,0,0,.35)',
    ].join(';')
    bar.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px">
        <span style="width:10px;height:10px;border-radius:99px;background:#f87171"></span>
        <span style="width:10px;height:10px;border-radius:99px;background:#fbbf24"></span>
        <span style="width:10px;height:10px;border-radius:99px;background:#34d399"></span>
        <span style="margin-left:8px;opacity:.8">Operating Swarm</span>
      </div>
      <div style="display:flex;align-items:center;gap:8px;background:#111;border:1px solid #3f3f46;border-radius:999px;padding:6px 12px">
        <span aria-hidden="true">🔒</span>
        <span data-testid="os-1391-capture-url">${href}</span>
      </div>
    `
    document.documentElement.style.setProperty('--os-1391-chrome-h', '68px')
    document.body.style.paddingTop = '68px'
  }, url)
}

async function main() {
  mkdirSync(OUT_DIR, { recursive: true })
  mkdirSync(ARTIFACT_DIR, { recursive: true })

  const browser = await chromium.launch({
    channel: 'chrome',
    headless: true,
    args: ['--no-sandbox', '--disable-gpu'],
  })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
  await stubApis(page)
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 })
  await page.getByRole('textbox', { name: 'Chat message' }).waitFor({ state: 'visible', timeout: 20_000 })
  await installUrlChrome(page, PAGE_URL)

  await page.evaluate(() => {
    window.dispatchEvent(
      new CustomEvent('swarm:open-agent-editor', { detail: { agentId: 'codey' } }),
    )
  })
  await page.getByTestId('agent-editor-tabs').waitFor({ state: 'visible', timeout: 10_000 })
  await page.getByTestId('agent-editor-tabs').getByRole('tab', { name: 'Memory' }).click()
  await page.getByTestId('agent-memory-panel').waitFor({ state: 'visible', timeout: 10_000 })
  await page.getByTestId('agent-memory-row-p1').waitFor({ state: 'visible' })
  await page.waitForTimeout(300)

  const panelPath = resolve(OUT_DIR, '1391-agent-memory-panel.png')
  await page.screenshot({ path: panelPath, fullPage: false })

  await page.getByTestId('agent-memory-export-preview').click()
  await page.getByTestId('memory-export-wizard').waitFor({ state: 'visible', timeout: 10_000 })
  await page.getByTestId('memory-export-reason-episode').waitFor({ state: 'visible' })
  await page.waitForTimeout(300)

  const wizardPath = resolve(OUT_DIR, '1391-memory-export-wizard.png')
  await page.screenshot({ path: wizardPath, fullPage: false })

  for (const file of [panelPath, wizardPath]) {
    const dest = resolve(ARTIFACT_DIR, file.split('/').pop())
    writeFileSync(dest, await (await import('node:fs')).promises.readFile(file))
  }

  await browser.close()
  console.log(JSON.stringify({ pageUrl: PAGE_URL, panelPath, wizardPath }, null, 2))
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
