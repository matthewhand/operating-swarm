/**
 * #1447 visual proof — Playwright / Vite harness.
 *
 * Unique product frames at `/__proof__/ia-1447` with the live URL in-frame.
 * Writes docs/screenshots/#1447-*.png and copies into ARTIFACTS_DIR when present.
 */
import { test, expect } from '@playwright/test'
import { copyFileSync, mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { artifactsDir } from './helpers/artifacts'

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const DOCS_DIR = path.join(REPO_ROOT, 'docs', 'screenshots')

const SHOTS = [
  {
    file: '#1447-computer-routines-no-agent-tab.png',
    surface: 'computer',
    expectDialog: true,
  },
  {
    file: '#1447-avatar-agent-config-sidepane.png',
    surface: 'config',
    expectDialog: false,
  },
] as const

test.describe('#1447 config vs routines IA', () => {
  test.use({ viewport: { width: 1280, height: 900 } })

  test.beforeEach(async ({ page }) => {
    await page.route('**/v1/blueprints**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: [] }),
      }),
    )
    await page.route('**/v1/models**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: [] }),
      }),
    )
    await page.route('**/health**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      }),
    )
  })

  for (const shot of SHOTS) {
    test(`captures ${shot.file}`, async ({ page }) => {
      const dest = path.join(DOCS_DIR, shot.file)
      const artifact = path.join(artifactsDir(), shot.file)
      mkdirSync(DOCS_DIR, { recursive: true })

      const url = `/__proof__/ia-1447?surface=${shot.surface}`
      await page.goto(url)
      await expect(page.getByTestId('ia-1447-proof')).toBeVisible()
      await expect(page.getByTestId('proof-url-1447')).toContainText('/__proof__/ia-1447')
      await expect(page.getByTestId('proof-url-1447')).toContainText(`surface=${shot.surface}`)

      const header = page.locator('header.os-chat-header')
      await expect(header).toBeVisible()
      await expect(header.getByTestId('header-avatar-generations')).toBeVisible()

      if (shot.expectDialog) {
        const dialog = page.getByRole('dialog', { name: 'Computer control' })
        await expect(dialog).toBeVisible()
        await expect(dialog.getByRole('tab', { name: 'Routines' })).toBeVisible()
        await expect(dialog.getByRole('tab', { name: 'Test schedule' })).toBeVisible()
        await expect(dialog.getByRole('tab', { name: 'Agent' })).toHaveCount(0)
        await expect(dialog.getByRole('heading', { name: 'Routines' })).toBeVisible()
      } else {
        await expect(page.getByTestId('agent-config-sidepane')).toBeVisible()
        await expect(page.getByTestId('agent-config-name-input')).toBeVisible()
        await expect(header.getByRole('button', { name: 'Edit agent' })).toBeVisible()
        await expect(page.getByRole('heading', { name: 'Routines' })).toHaveCount(0)
      }

      await page.screenshot({ path: dest, fullPage: true })
      copyFileSync(dest, artifact)
    })
  }
})
