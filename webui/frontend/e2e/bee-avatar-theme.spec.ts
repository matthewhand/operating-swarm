import { test, expect } from '@playwright/test'
import path from 'node:path'
import { artifactsDir } from './helpers/artifacts'

async function stubApis(page: import('@playwright/test').Page) {
  await page.route('**/v1/blueprints**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'list', data: [] }),
    })
  })
  await page.route('**/v1/models**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'list', data: [] }),
    })
  })
  await page.route('**/v1/teams**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'list', data: [] }),
    })
  })
  await page.route('**/health**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok' }),
    })
  })
}

/**
 * Bee is an optional install (REQ-828 / #820): Blobs stay the factory default
 * and Bee is never auto-applied — the user installs it in Settings → Rail, and
 * the rail only repaints once Bee is the theme in force.
 *
 * Rewritten for the restored installable-themes UI (#86). The previous version
 * asserted a `select` labelled "Avatar theme" with Default/Blobs/Bee options;
 * that control no longer exists — Settings now installs theme *families* as
 * checkboxes and the per-agent picker chooses inside that set.
 */
test('Bee theme is opt-in and paints both locked variants', async ({ page }) => {
  const ARTIFACTS = artifactsDir()
  await stubApis(page)
  await page.goto('/chat')

  await expect(page.getByRole('button', { name: 'Open settings' })).toBeVisible()
  await expect(page.locator('svg[data-avatar-theme="blobs"]').first()).toBeAttached()
  await expect(page.locator('svg[data-avatar-theme="bee"]')).toHaveCount(0)
  await page.screenshot({
    path: path.join(ARTIFACTS, 'bee_theme_default_still_blobs.png'),
    fullPage: true,
  })

  await page.getByRole('button', { name: 'Open settings' }).click()
  const dialog = page.getByRole('dialog', { name: 'Settings' })
  await expect(dialog).toBeVisible()
  await page.getByRole('button', { name: 'Rail' }).click()

  // Installed themes: only Blobs, and it is locked on while it is the sole
  // installed family. Bee is available but not installed.
  const themes = dialog.getByTestId('installed-avatar-themes')
  await expect(themes).toBeVisible()
  const beeToggle = themes.getByRole('checkbox', { name: 'Bee' })
  const blobsToggle = themes.getByRole('checkbox', { name: 'Blobs' })
  await expect(blobsToggle).toBeChecked()
  await expect(blobsToggle).toBeDisabled()
  await expect(beeToggle).not.toBeChecked()
  await expect(dialog.getByText(/never auto-applied/i)).toBeVisible()
  await expect(dialog.getByText(/optional installs/i)).toBeVisible()
  await page.screenshot({
    path: path.join(ARTIFACTS, 'bee_theme_settings_installed_themes.png'),
  })

  // Installing Bee must not repaint anything on its own — it is an install,
  // not a theme switch.
  await beeToggle.check()
  await expect(beeToggle).toBeChecked()
  await expect(blobsToggle).toBeEnabled()
  await expect(page.locator('svg[data-avatar-theme="bee"]')).toHaveCount(0)

  // With Bee as the sole installed theme it is the theme in force, and the rail
  // paints both locked variants.
  await blobsToggle.uncheck()
  await expect(blobsToggle).not.toBeChecked()

  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()

  await expect(page.locator('svg[data-avatar-theme="bee"]').first()).toBeAttached()
  await expect(page.locator('svg[data-bee-variant="side-on"]').first()).toBeAttached()
  await expect(page.locator('svg[data-bee-variant="face-only"]').first()).toBeAttached()
  await expect(page.locator('[data-googly="true"]').first()).toBeAttached()
  await expect(page.locator('svg[data-avatar-theme="bee"]').first()).toHaveAttribute('data-bee-accessory')
  await page.screenshot({
    path: path.join(ARTIFACTS, 'bee_theme_rail_both_variants.png'),
    fullPage: true,
  })
})
