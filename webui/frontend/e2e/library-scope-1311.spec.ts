/**
 * #1311 visual proof. Real Blueprints pane on `/__proof__/library-1311`,
 * talking to the dev API (rosters, publish, preset, import).
 */
import { test, expect, type Page } from '@playwright/test'
import { copyFileSync, mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { artifactsDir } from './helpers/artifacts'

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const DOCS_DIR = path.join(REPO_ROOT, 'docs', 'screenshots')

async function markStep(page: Page, step: string) {
  await page.evaluate((next) => {
    const url = new URL(window.location.href)
    url.searchParams.set('step', next)
    window.history.pushState({}, '', url)
    window.dispatchEvent(new PopStateEvent('popstate'))
  }, step)
  await expect(page.getByTestId('proof-url-1311')).toContainText(`/__proof__/library-1311`)
  await expect(page.getByTestId('proof-url-1311')).toContainText(`step=${step}`)
}

async function shot(page: Page, file: string) {
  const dest = path.join(DOCS_DIR, file)
  mkdirSync(DOCS_DIR, { recursive: true })
  await page.screenshot({ path: dest, fullPage: false })
  copyFileSync(dest, path.join(artifactsDir(), file))
}

test.describe('#1311 library scope', () => {
  test.use({ viewport: { width: 1280, height: 900 } })
  test.setTimeout(90_000)

  test('mine, team publish, preset rail, and missing import', async ({ page }) => {
    await page.goto('/login/')
    await page.locator('#username').fill('ada')
    await page.locator('#password').fill('not-used')
    await page.locator('form button[type="submit"], form input[type="submit"]').first().click()
    await page.waitForLoadState('domcontentloaded')

    await page.goto('/__proof__/library-1311?step=mine')
    const library = page.getByTestId('library-scope')
    await expect(page.getByRole('heading', { name: 'Blueprints' })).toBeVisible()
    await expect(library.getByRole('button', { name: 'Mine' })).toHaveAttribute('aria-pressed', 'true')
    await expect(library.getByText('Mine keeps the personal library.')).toBeVisible()
    await expect(library.getByRole('button', { name: 'Add Support to rail' })).toBeVisible()
    await shot(page, '#1311-mine-presets.png')

    const firstBlueprint = page.getByRole('listbox', { name: 'Blueprints' }).getByRole('option').first()
    await expect(firstBlueprint).toBeVisible()
    await firstBlueprint.click()
    await library.getByRole('button', { name: 'Team' }).click()
    await expect(library.locator('[data-testid=library-team-picker] option', { hasText: 'Engineering' })).toBeAttached()
    await library.getByRole('combobox', { name: 'Team' }).selectOption({ label: 'Engineering' })
    await expect(library.getByRole('button', { name: 'Publish' })).toBeEnabled()
    await markStep(page, 'team')
    await shot(page, '#1311-team-publish.png')
    await library.getByRole('button', { name: 'Publish' }).click()
    await expect(library.getByTestId('library-scope-notice')).toContainText('Blueprint published.')

    await library.getByRole('button', { name: 'Add Support to rail' }).click()
    await expect(library.getByTestId('library-scope-notice')).toContainText('Support is on the rail.', {
      timeout: 30_000,
    })
    await markStep(page, 'preset')
    await shot(page, '#1311-preset-on-rail.png')

    await library.getByRole('button', { name: 'Organisation' }).click()
    await expect(library.getByRole('button', { name: 'Import' }).first()).toBeVisible()
    await library.getByRole('button', { name: 'Import' }).first().click()
    await expect(library.getByTestId('library-scope-notice')).toContainText('Imported. Missing:')
    await markStep(page, 'import')
    await shot(page, '#1311-import-missing.png')
  })
})
