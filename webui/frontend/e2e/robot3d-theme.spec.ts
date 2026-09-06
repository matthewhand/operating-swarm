import { test, expect } from '@playwright/test'

test('Rail avatar theme offers an enabled 3D robot option (REQ-194 Phase 1)', async ({
  page,
}) => {
  await page.route('**/v1/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'list', data: [], configured: [], kinds: [], profiles: [] }),
    })
  })
  await page.goto('/chat')
  await page.getByRole('button', { name: 'Open settings' }).click()
  const dialog = page.getByRole('dialog', { name: 'Settings' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Rail' }).click()

  const picker = page.getByLabel('Avatar theme')
  await expect(picker).toBeVisible()
  await expect(picker).toHaveValue('blobs')

  const robot3d = page.locator('#os-avatar-theme option[value="robot3d"]')
  await expect(robot3d).toHaveText('3D robot')
  await expect(robot3d).not.toBeDisabled()
  const adr = page.getByRole('link', { name: 'ADR-008' })
  await expect(adr).toBeVisible()
  await expect(adr).toHaveAttribute(
    'href',
    'https://github.com/matthewhand/open-swarm/blob/main/docs/adr/008-3d-robot-avatar-theme.md',
  )

  // Selecting robot3d persists the theme (no longer a reserved non-value).
  await picker.selectOption('robot3d')
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('swarm_avatar_theme')))
    .toBe('robot3d')

  // The combo sub-picker appears only while robot3d is active.
  await expect(page.getByTestId('robot3d-combo-picker')).toBeVisible()

})