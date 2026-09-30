#!/usr/bin/env node
/**
 * #1393 unique product screenshots (Skeptic visual proof).
 *
 * Hermetic Playwright capture of the SPA skills editor, invalid pack picker,
 * and first-chat getting-started chip. Injects identifying chrome with the
 * issue id + route. No secrets. No live LLM.
 *
 * Usage (from repo root, with Vite already serving the SPA):
 *   PLAYWRIGHT_BASE_URL=http://127.0.0.1:5173 node scripts/capture_1393_skills_spa.mjs
 */
import { mkdirSync, copyFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '../webui/frontend/node_modules/playwright/index.mjs'

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const BASE = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5173'
const OUT_DIR = path.join(REPO, 'docs', 'screenshots', '1393')
const ARTIFACT_DIR = process.env.ARTIFACTS_DIR || '/opt/cursor/artifacts'

const WELCOME = {
  name: 'welcome-tour',
  description: 'Walk the first conversation.',
  instructions: 'Greet the operator and list three first steps.',
  source: 'authored',
}
const REVIEW = {
  name: 'review-notes',
  description: 'When reviewing a diff.',
  instructions: 'Review the diff in order.',
  source: 'authored',
}

const SKILLS_LIST = {
  object: 'agent_skill_list',
  agent_id: 'codey',
  first_run_pending: true,
  gettingStarted: { skill: 'welcome-tour' },
  skills: [WELCOME, REVIEW],
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

  await page.route('**/*', async (route) => {
    const parsed = new URL(route.request().url())
    const path = parsed.pathname
    const method = route.request().method()
    if (path.includes('/v1/agents/') && path.includes('/skills')) {
      if (method === 'POST') {
        return json(route, { object: 'agent_skill', agent_id: 'codey', ...WELCOME }, 201)
      }
      return json(route, SKILLS_LIST)
    }
    if (path === '/v1/skills/' || path === '/v1/skills') {
      return json(route, {
        object: 'list',
        data: [
          {
            name: 'conventional-commit',
            description: 'Write a conventional commit.',
            assets: [],
          },
        ],
      })
    }
    if (path.startsWith('/v1/blueprints')) return json(route, BLUEPRINTS)
    if (path.startsWith('/chat/thread')) {
      return json(route, {
        agent_id: 'codey',
        conversation_id: 'conv-1393',
        messages: [],
      })
    }
    if (path.includes('/v1/agents/') && path.includes('/settings')) {
      return json(route, {
        agent_id: 'codey',
        new_chat_per_task: false,
        use_suggestions: false,
      })
    }
    if (path.includes('/suggestions/')) {
      return json(route, { object: 'suggestions', suggestions: [] })
    }
    if (path.startsWith('/v1/models')) return json(route, { object: 'list', data: [] })
    if (path.startsWith('/v1/cli-agents')) return json(route, { clis: [] })
    if (path.startsWith('/v1/llm-profiles') || path.includes('/llm-profiles')) {
      return json(route, { profiles: [] })
    }
    if (path.startsWith('/v1/remotes')) return json(route, { object: 'list', data: [] })
    if (path.startsWith('/v1/team-rosters') || path.includes('team_rosters')) {
      return json(route, { object: 'list', data: [] })
    }
    if (path.startsWith('/v1/image-gen') || path.includes('/image-gen')) {
      return json(route, {})
    }
    if (path === '/health' || path === '/health/') return json(route, { status: 'ok' })
    return route.continue()
  })
}

async function injectChrome(page, label) {
  await page.evaluate((text) => {
    const id = 'os-1393-capture-chrome'
    let bar = document.getElementById(id)
    if (!bar) {
      bar = document.createElement('div')
      bar.id = id
      bar.setAttribute('data-testid', 'os-1393-capture-chrome')
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

async function openEditor(page) {
  await page.evaluate(() => {
    window.dispatchEvent(
      new CustomEvent('swarm:open-agent-editor', { detail: { agentId: 'codey' } }),
    )
  })
  await page.getByRole('dialog', { name: /Edit /i }).waitFor({ state: 'visible' })
  await page.locator('#os-agent-editor').waitFor({ state: 'visible' })
  await page.getByRole('tab', { name: 'Model & inference' }).click()
  await page.getByTestId('agent-skills-editor').waitFor({ state: 'visible' })
}

async function closeEditor(page) {
  const conceal = page.getByTestId('sidepane-conceal')
  if (await conceal.isVisible().catch(() => false)) {
    await conceal.click()
  } else {
    await page.keyboard.press('Escape')
  }
  await page.getByRole('dialog', { name: /Edit /i }).waitFor({ state: 'hidden' })
}

async function main() {
  mkdirSync(OUT_DIR, { recursive: true })
  mkdirSync(ARTIFACT_DIR, { recursive: true })

  const executablePath =
    process.env.CHROME_PATH ||
    '/usr/bin/google-chrome-stable'
  const browser = await chromium.launch({
    headless: true,
    executablePath,
    args: ['--no-sandbox', '--disable-gpu'],
  })
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } })
  await stubApis(page)

  const shots = []

  await page.goto(`${BASE}/chat?blueprint=codey#1393-skills-editor`, {
    waitUntil: 'domcontentloaded',
  })
  await page.getByRole('textbox', { name: 'Chat message' }).waitFor({ timeout: 20_000 })
  await openEditor(page)
  await injectChrome(
    page,
    `#1393  ${BASE}/chat?blueprint=codey#1393-skills-editor  ·  skills editor · When to use`,
  )
  await page.getByTestId('agent-skill-when-welcome-tour').waitFor()
  await page.getByTestId('agent-skill-create-when').scrollIntoViewIfNeeded()
  const editorPath = path.join(OUT_DIR, '#1393-skills-editor.png')
  await page.screenshot({ path: editorPath, fullPage: false })
  shots.push(editorPath)

  await page.evaluate(() => {
    history.replaceState(null, '', '/chat?blueprint=codey#1393-pack-picker-invalid')
  })
  const welcomeBox = page.getByTestId('agent-pack-skill-welcome-tour')
  await welcomeBox.scrollIntoViewIfNeeded()
  if (await welcomeBox.isChecked()) {
    await welcomeBox.click()
  }
  await page.getByTestId('agent-pack-getting-started').selectOption('')
  await page.getByTestId('agent-pack-export-hint').waitFor()
  await page.getByTestId('agent-pack-picker').scrollIntoViewIfNeeded()
  await injectChrome(
    page,
    `#1393  ${BASE}/chat?blueprint=codey#1393-pack-picker-invalid  ·  export disabled · gettingStarted not in selection`,
  )
  const pickerPath = path.join(OUT_DIR, '#1393-pack-picker-invalid.png')
  await page.screenshot({ path: pickerPath, fullPage: false })
  shots.push(pickerPath)

  await closeEditor(page)
  await page.getByTestId('getting-started-flow').waitFor({ timeout: 20_000 })
  await page.evaluate(() => {
    history.replaceState(null, '', '/chat?blueprint=codey#1393-first-chat')
  })
  await injectChrome(
    page,
    `#1393  ${BASE}/chat?blueprint=codey#1393-first-chat  ·  first chat · getting-started when-to-use chip`,
  )
  const chatPath = path.join(OUT_DIR, '#1393-first-chat-getting-started.png')
  await page.screenshot({ path: chatPath, fullPage: false })
  shots.push(chatPath)

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
