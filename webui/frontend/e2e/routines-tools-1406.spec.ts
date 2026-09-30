/**
 * #1406 visual proof — Playwright / Vite harness.
 *
 * Captures unique product frames of the + Add Tool or MCP picker and
 * add/remove list at `/__proof__/routines-1406` with the live URL in-frame.
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
    file: '#1406-dialog-picker.png',
    surface: 'dialog',
    state: 'picker',
    clickRow: false,
    expectPicker: true,
    expectChip: false,
  },
  {
    file: '#1406-dialog-added-remove.png',
    surface: 'dialog',
    state: 'added',
    clickRow: false,
    expectPicker: false,
    expectChip: true,
  },
  {
    file: '#1406-pane-added-remove.png',
    surface: 'pane',
    state: 'pane-added',
    clickRow: true,
    expectPicker: false,
    expectChip: true,
  },
  {
    file: '#1406-dialog-disabled-reason.png',
    surface: 'dialog',
    state: 'disabled',
    clickRow: false,
    expectPicker: true,
    expectChip: false,
  },
] as const

test.describe('#1406 Add Tool or MCP picker', () => {
  test.use({ viewport: { width: 1280, height: 1100 } })

  test.beforeEach(async ({ page }) => {
    await page.route('**/v1/blueprints**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: [] }) }),
    )
    await page.route('**/v1/models**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: [] }) }),
    )
    await page.route('**/health**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) }),
    )
  })

  for (const shot of SHOTS) {
    test(`captures ${shot.file}`, async ({ page }) => {
      const dest = path.join(DOCS_DIR, shot.file)
      const artifact = path.join(artifactsDir(), shot.file)
      mkdirSync(DOCS_DIR, { recursive: true })

      const url = `/__proof__/routines-1406?surface=${shot.surface}&state=${shot.state}`
      await page.goto(url)
      await expect(page.getByTestId('routine-tools-proof-1406')).toBeVisible()
      await expect(page.getByTestId('proof-url-1406')).toContainText('/__proof__/routines-1406')
      await expect(page.getByTestId('proof-url-1406')).toContainText(`surface=${shot.surface}`)
      await expect(page.getByTestId('proof-url-1406')).toContainText(`state=${shot.state}`)

      if (shot.clickRow) {
        await page.getByRole('button', { name: /Search recap/ }).click()
        await expect(page.getByTestId('routine-editor')).toBeVisible()
      } else {
        await expect(page.getByTestId('routine-editor-dialog')).toBeVisible()
      }

      await expect(page.getByTestId('routine-add-tool-or-mcp')).toBeVisible()

      if (shot.expectPicker) {
        await expect(page.getByTestId('routine-tool-picker')).toBeVisible()
        await page.getByTestId('routine-tool-picker').scrollIntoViewIfNeeded()
        await expect(page.getByTestId('routine-tool-pick-web_search')).toBeVisible()
        if (shot.state === 'disabled') {
          await page.getByTestId('routine-tool-picker-search').fill('brave')
          await expect(page.getByTestId('routine-tool-reason-brave_search')).toContainText('BRAVE_API_KEY')
          await page.getByTestId('routine-tool-reason-brave_search').scrollIntoViewIfNeeded()
        } else {
          await expect(page.getByTestId('routine-tool-pick-web_search')).toBeVisible()
        }
      }

      if (shot.expectChip) {
        await expect(page.getByTestId('routine-tool-chip-web_search')).toBeVisible()
        await expect(page.getByTestId('routine-tool-remove-web_search')).toBeVisible()
      }

      await page.screenshot({ path: dest, fullPage: true })
      copyFileSync(dest, artifact)
    })
  }
})
