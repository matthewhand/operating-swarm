#!/usr/bin/env node
/**
 * #1676 unique path-in-frame screenshots (centered pill + edit pane open).
 * Dark mode + wait for document fonts. No secrets.
 *
 * Usage (repo root of this worktree, Vite already serving):
 *   PLAYWRIGHT_BASE_URL=http://127.0.0.1:5173 node scripts/capture_1676_agent_pill.mjs
 */
import { mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '../webui/frontend/node_modules/playwright/index.mjs'

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const BASE = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5173'
const OUT_DIR = path.join(REPO, 'docs', 'screenshots', '1676')
const CHROME = process.env.CHROME_PATH || 'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe'

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
  const browser = await chromium.launch({
    headless: true,
    executablePath: CHROME,
  })
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    colorScheme: 'dark',
  })
  const page = await context.newPage()

  const pillUrl = `${BASE}/__proof__/agent-pill-1676?theme=dark&surface=pill`
  await page.goto(pillUrl, { waitUntil: 'networkidle' })
  await page.getByTestId('selected-agent-header').waitFor({ state: 'visible' })
  await page.getByTestId('proof-url-1676').waitFor({ state: 'visible' })
  await shot(page, '#1676-agent-pill-centered-dark.png')

  const editUrl = `${BASE}/__proof__/agent-pill-1676?theme=dark&surface=edit`
  await page.goto(editUrl, { waitUntil: 'networkidle' })
  await page.getByTestId('selected-agent-header').waitFor({ state: 'visible' })
  // Sidepane should open after auto-click
  await page.waitForSelector('[data-testid="agent-config-sidepane"], [role="dialog"], .os-agent-config-sidepane, [data-sidepane="agent-config"]', {
    timeout: 8000,
  }).catch(() => null)
  // Fallback: click pill if auto-open missed
  const paneVisible = await page.locator('[data-testid="agent-config-sidepane"]').isVisible().catch(() => false)
  if (!paneVisible) {
    await page.getByTestId('selected-agent-header').click()
    await page.waitForTimeout(400)
  }
  await shot(page, '#1676-agent-pill-edit-pane-dark.png')

  await browser.close()
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})