import { test, expect } from '@playwright/test'

const FIXTURE = 'REQ-48 fixture stays mounted'

async function stubApis(page: import('@playwright/test').Page) {
  await page.route('**/chat/thread/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        agent_id: 'support',
        conversation_id: 'agt-req48',
        messages: [{ role: 'user', content: FIXTURE }],
      }),
    })
  })
  await page.route('**/v1/blueprints**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        object: 'list',
        data: [{ id: 'support', name: 'Support', description: 'Helper' }],
      }),
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
      body: JSON.stringify({
        object: 'list',
        data: [{ id: 'lab', object: 'team', description: 'Lab', llm_profile: 'default' }],
      }),
    })
  })
}

test('Settings and Teams sheets open over a fixture chat message', async ({ page }) => {
  const jsErrors: string[] = []
  page.on('pageerror', (e) => jsErrors.push(e.message))
  await stubApis(page)
  await page.goto('/chat')

  await expect(page.getByText(FIXTURE)).toBeVisible()
  // Settings and Teams are no longer composer "Add" menu items: the gear opens
  // Settings and the rail footer carries the Teams popup above Plugins.
  await page.getByRole('button', { name: 'Open settings' }).click()

  const settings = page.getByRole('dialog', { name: 'Settings' })
  await expect(settings).toBeVisible()
  await expect(settings).toHaveClass(/modal-end/)
  await expect(page.getByText(FIXTURE)).toBeVisible()
  await expect(page).toHaveURL(/\/chat/)

  await settings.getByRole('button', { name: /^Close$/ }).click()
  await expect(settings).toBeHidden()
  await expect(page.getByRole('textbox', { name: 'Chat message' })).toBeVisible()

  // The rail footer Teams button opens the two-pane team composer ("New team").
  await page.getByTestId('os-teams-button').click()
  const teams = page.getByRole('dialog', { name: 'New team' })
  await expect(teams).toBeVisible()
  await expect(page.getByText(FIXTURE)).toBeVisible()
  // The shared DaisyUI Modal closes on Escape (native cancel) — its backdrop
  // button sits inside an aria-hidden form, so it is not reachable by role.
  await page.keyboard.press('Escape')
  await expect(teams).toBeHidden()
  await expect(page.getByRole('textbox', { name: 'Chat message' })).toBeVisible()

  expect(jsErrors, `uncaught JS errors: ${jsErrors.join(' | ')}`).toHaveLength(0)
})

test('Search overlay traps Tab inside the dialog', async ({ page }) => {
  await stubApis(page)
  await page.goto('/chat')
  await page.getByRole('button', { name: 'Search' }).click()
  const dialog = page.getByRole('dialog', { name: 'Search' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('combobox', { name: 'Search' })).toBeFocused()

  for (let i = 0; i < 12; i++) {
    await page.keyboard.press('Tab')
    const inside = await page.evaluate(() => {
      const el = document.querySelector('[role="dialog"][aria-label="Search"]')
      const active = document.activeElement
      return Boolean(el && active && el.contains(active))
    })
    expect(inside, `Tab ${i + 1} left the Search dialog`).toBe(true)
  }
})
