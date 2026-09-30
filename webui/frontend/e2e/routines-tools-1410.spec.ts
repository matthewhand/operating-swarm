/**
 * #1410 visual proof — Playwright / Vite harness.
 *
 * Captures unique product frames of instruction-gap tool suggestions at
 * `/__proof__/routines-1410` with the live URL in-frame.
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
    file: '#1410-dialog-pr-suggest.png',
    surface: 'dialog',
    state: 'pr',
    clickRow: false,
    expectSuggest: 'routine-tool-suggest-open_pull_request',
    expectQuiet: false,
  },
  {
    file: '#1410-dialog-memory-suggest.png',
    surface: 'dialog',
    state: 'memory',
    clickRow: false,
    expectSuggest: 'routine-tool-suggest-memories',
    expectQuiet: false,
  },
  {
    file: '#1410-dialog-present-quiet.png',
    surface: 'dialog',
    state: 'present',
    clickRow: false,
    expectSuggest: '',
    expectQuiet: true,
  },
  {
    file: '#1410-dialog-dismissed.png',
    surface: 'dialog',
    state: 'dismissed',
    clickRow: false,
    expectSuggest: '',
    expectQuiet: true,
  },
  {
    file: '#1410-pane-pr-suggest.png',
    surface: 'pane',
    state: 'pane-pr',
    clickRow: true,
    expectSuggest: 'routine-tool-suggest-open_pull_request',
    expectQuiet: false,
  },
] as const

test.describe('#1410 instruction-gap tool suggestions', () => {
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

      const url = `/__proof__/routines-1410?surface=${shot.surface}&state=${shot.state}`
      await page.goto(url)
      await expect(page.getByTestId('routine-tools-proof-1410')).toBeVisible()
      await expect(page.getByTestId('proof-url-1410')).toContainText('/__proof__/routines-1410')
      await expect(page.getByTestId('proof-url-1410')).toContainText(`surface=${shot.surface}`)
      await expect(page.getByTestId('proof-url-1410')).toContainText(`state=${shot.state}`)

      if (shot.clickRow) {
        await page.getByRole('button', { name: /Issue follow-up/ }).click()
        await expect(page.getByTestId('routine-editor')).toBeVisible()
      } else {
        await expect(page.getByTestId('routine-editor-dialog')).toBeVisible()
      }

      if (shot.expectSuggest) {
        await expect(page.getByTestId(shot.expectSuggest)).toBeVisible()
        await page.getByTestId(shot.expectSuggest).scrollIntoViewIfNeeded()
      }

      if (shot.expectQuiet) {
        await expect(page.getByTestId('routine-tools')).toBeVisible()
        await expect(page.getByTestId('routine-tool-suggestions')).toHaveCount(0)
      }

      await page.screenshot({ path: dest, fullPage: true })
      copyFileSync(dest, artifact)
    })
  }
})
