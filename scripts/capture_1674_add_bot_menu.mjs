#!/usr/bin/env node
/**
 * #1674 unique path-in-frame screenshot: open Add Bot dropdown (dark + fonts).
 * Usage: PLAYWRIGHT_BASE_URL=http://127.0.0.1:5173 node scripts/capture_1674_add_bot_menu.mjs
 */
import { mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '../webui/frontend/node_modules/playwright/index.mjs'

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const BASE = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5173'
const OUT_DIR = path.join(REPO, 'docs', 'screenshots', '1674')
const CHROME = process.env.CHROME_PATH || 'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe'

async function main() {
  mkdirSync(OUT_DIR, { recursive: true })
  const browser = await chromium.launch({ headless: true, executablePath: CHROME })
  const page = await (await browser.newContext({
    viewport: { width: 1280, height: 800 },
    colorScheme: 'dark',
  })).newPage()

  const url = `${BASE}/__proof__/add-bot-1674?theme=dark`
  await page.goto(url, { waitUntil: 'networkidle' })
  await page.getByTestId('add-bot-menu-trigger').waitFor({ state: 'visible' })
  // Proof auto-clicks; if panel not open yet, click once.
  const panel = page.getByTestId('os-add-bot-menu')
  if (!(await panel.isVisible().catch(() => false))) {
    await page.getByTestId('add-bot-menu-trigger').click()
  }
  await panel.waitFor({ state: 'visible' })
  await page.getByTestId('os-add-bot-menu-create-bot').waitFor({ state: 'visible' })
  await page.getByTestId('os-add-bot-menu-create-group').waitFor({ state: 'visible' })
  await page.getByTestId('os-add-bot-menu-agents').waitFor({ state: 'visible' })
  await page.getByTestId('proof-url-1674').waitFor({ state: 'visible' })
  await page.evaluate(async () => { if (document.fonts?.ready) await document.fonts.ready })

  const dest = path.join(OUT_DIR, '#1674-add-bot-menu-open-dark.png')
  await page.screenshot({ path: dest, fullPage: false })
  console.log('wrote', dest)
  await browser.close()
}

main().catch((e) => { console.error(e); process.exit(1) })
