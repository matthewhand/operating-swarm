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

  // Settings installs theme families as checkboxes now (REQ-828): the old
  // single `select#os-avatar-theme` no longer exists.
  const themes = dialog.getByTestId('installed-avatar-themes')
  await expect(themes).toBeVisible()

  const robot3d = themes.getByRole('checkbox', { name: '3D robot' })
  await expect(robot3d).toBeVisible()
  await expect(robot3d).not.toBeDisabled()
  const adr = page.getByRole('link', { name: 'ADR-008' })
  await expect(adr).toBeVisible()
  await expect(adr).toHaveAttribute(
    'href',
    'https://github.com/matthewhand/open-swarm/blob/main/docs/adr/008-3d-robot-avatar-theme.md',
  )

  // Installing 3D robot alone puts it in force (no longer a reserved non-value).
  await robot3d.check()
  await themes.getByRole('checkbox', { name: 'Blobs' }).uncheck()
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('swarm_avatar_theme')))
    .toBe('robot3d')

  // The combo sub-picker appears only while robot3d is active.
  await expect(page.getByTestId('robot3d-combo-picker')).toBeVisible()
})