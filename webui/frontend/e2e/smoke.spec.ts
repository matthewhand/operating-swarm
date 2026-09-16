import { test, expect } from '@playwright/test'

// Smoke test: the SPA shell loads and renders without crashing.
// NOTE: the preview build runs without a backend, so failed API fetches are
// expected — we hard-fail only on UNCAUGHT JS errors (pageerror), and record
// console.error (network/API) as informational, not a failure.
test('app shell loads and renders without uncaught JS errors', async ({ page }) => {
  const jsErrors: string[] = []
  const consoleErrors: string[] = []
  page.on('pageerror', (e) => jsErrors.push(e.message))
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text())
  })

  await page.goto('/')

  await expect(page).toHaveTitle(/^Operating Swarm$/)
  await expect(page.locator('#root')).not.toBeEmpty()
  await expect(page.getByRole('button', { name: 'Search' })).toBeVisible()
  await expect(page.getByRole('textbox', { name: 'Chat message' })).toBeVisible()

  if (consoleErrors.length) {
    console.log(`[smoke] ${consoleErrors.length} console error(s) (expected w/o backend): ` +
      consoleErrors.slice(0, 5).join(' | '))
  }

  expect(jsErrors, `uncaught JS errors: ${jsErrors.join(' | ')}`).toHaveLength(0)
})
