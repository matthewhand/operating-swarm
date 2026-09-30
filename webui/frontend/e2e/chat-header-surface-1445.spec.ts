/**
 * #1445 visual proof — chat header only on a chat route with a valid seat.
 *
 * AnythingLLM chrome is present on `/chat?remote=anythingllm`, absent while
 * Settings is open (button and `/chat?settings=true`), and absent on `/agents`.
 * Each shot stamps the landed path in-frame (headless Chromium has no URL bar).
 */
import { test, expect, type Page } from '@playwright/test'
import { copyFileSync, mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { artifactsDir } from './helpers/artifacts'

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const DOCS_DIR = path.join(REPO_ROOT, 'docs', 'screenshots')

const EMPTY_LIST = { object: 'list', data: [] }

const REMOTES = {
  object: 'list',
  kinds: [{ id: 'anythingllm', label: 'AnythingLLM' }],
  configured: [
    {
      id: 'anythingllm',
      kind: 'anythingllm',
      title: 'AnythingLLM',
      source: 'config',
      base_url: 'http://127.0.0.1:3001',
      capabilities: { list: true, send: true, sessions: true },
    },
  ],
}

async function stubApis(page: Page) {
  await page.route('**/v1/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(EMPTY_LIST),
    }),
  )
  await page.route('**/v1/remotes**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(REMOTES),
    }),
  )
  await page.route('**/health**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok' }),
    }),
  )
  await page.route('**/chat/thread**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        agent_id: 'anythingllm',
        conversation_id: 'header-1445',
        messages: [],
        summaries: [],
      }),
    }),
  )
  await page.route('**/operate/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        remote: 'anythingllm',
        op: 'list',
        ok: true,
        data: { agents: [], sessions: [] },
      }),
    }),
  )
}

async function stampPath(page: Page, landed: string) {
  const live = new URL(page.url())
  const label = `#1445 ${landed} → ${live.pathname}${live.search}`
  await page.evaluate((text) => {
    const id = 'proof-url-1445'
    let el = document.getElementById(id)
    if (!el) {
      el = document.createElement('div')
      el.id = id
      el.setAttribute('data-testid', 'proof-url-1445')
      el.style.position = 'fixed'
      el.style.top = '0'
      el.style.left = '0'
      el.style.right = '0'
      el.style.zIndex = '2147483647'
      el.style.background = '#111111'
      el.style.color = '#ffffff'
      el.style.font = '14px/1.4 ui-monospace, monospace'
      el.style.padding = '8px 12px'
      document.body.appendChild(el)
      const pad = Number.parseFloat(document.body.style.paddingTop || '0')
      if (pad < 36) document.body.style.paddingTop = '36px'
    }
    el.textContent = text
  }, label)
  await expect(page.getByTestId('proof-url-1445')).toContainText(landed)
  return label
}

async function saveShot(page: Page, file: string) {
  mkdirSync(DOCS_DIR, { recursive: true })
  const dest = path.join(DOCS_DIR, file)
  await page.screenshot({ path: dest, fullPage: false })
  copyFileSync(dest, path.join(artifactsDir(), file))
}

test.describe('#1445 chat header surface', () => {
  test.use({ viewport: { width: 1280, height: 900 } })

  test.beforeEach(async ({ page }) => {
    await stubApis(page)
  })

  test('AnythingLLM header on a valid chat seat', async ({ page }) => {
    const landed = '/chat?remote=anythingllm'
    await page.goto(landed)
    const header = page.getByTestId('selected-agent-header')
    await expect(header).toBeVisible()
    await expect(header).toHaveAttribute('data-seat', 'remote:anythingllm')
    await expect(header).toContainText('AnythingLLM')
    await stampPath(page, landed)
    await saveShot(page, '#1445-chat-anythingllm-header.png')
  })

  test('Settings deep link clears the AnythingLLM header', async ({ page }) => {
    const landed = '/chat?remote=anythingllm&settings=true'
    await page.goto(landed)
    const dialog = page.getByRole('dialog', { name: 'Settings' })
    await expect(dialog).toBeVisible()
    await expect(page.getByTestId('selected-agent-header')).toHaveCount(0)
    await expect(page.locator('header.os-chat-header')).toHaveCount(0)
    await expect(page.getByRole('textbox', { name: 'Chat message' })).toBeVisible()
    await stampPath(page, landed)
    await saveShot(page, '#1445-settings-deeplink-header-cleared.png')
  })

  test('closing Settings restores the AnythingLLM header', async ({ page }) => {
    const landed = '/chat?remote=anythingllm'
    await page.goto(landed)
    await expect(page.getByTestId('selected-agent-header')).toBeVisible()
    await page.getByRole('button', { name: 'Open settings' }).click()
    const dialog = page.getByRole('dialog', { name: 'Settings' })
    await expect(dialog).toBeVisible()
    await expect(page.getByTestId('selected-agent-header')).toHaveCount(0)
    await dialog.getByRole('button', { name: 'Close' }).click()
    const header = page.getByTestId('selected-agent-header')
    await expect(header).toBeVisible()
    await expect(header).toHaveAttribute('data-seat', 'remote:anythingllm')
    await stampPath(page, `${landed} settings-closed`)
    await saveShot(page, '#1445-settings-closed-header-restored.png')
  })

  test('Agent Router has no chat header', async ({ page }) => {
    const landed = '/agents'
    await page.goto(landed)
    await expect(page.getByTestId('agents-chat-header')).toBeVisible()
    await expect(page.getByTestId('selected-agent-header')).toHaveCount(0)
    await expect(page.locator('header.os-chat-header')).toHaveCount(0)
    await stampPath(page, landed)
    await saveShot(page, '#1445-agents-no-chat-header.png')
  })
})
