import { test, expect } from '@playwright/test'

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
      body: JSON.stringify({
        object: 'list',
        data: [{ id: 'default', object: 'model', created: 0, owned_by: 'swarm' }],
      }),
    })
  })
  await page.route('**/v1/llm-profiles**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        object: 'llm_profiles',
        profiles: [
          { id: 'gpt-5.6-terra', object: 'llm_profile', source: 'config', owned_by: 'openai' },
        ],
        default_llm_profile: 'gpt-5.6-terra',
        default_is_auto: true,
        override_per_task: false,
        task_llm_profiles: {},
        auto_picks: { default: 'gpt-5.6-terra' },
        warnings: [],
        routes: {},
        task_classes: ['orchestration', 'auxiliary', 'delegation'],
      }),
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
  await page.route('**/v1/system**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        path: '~/share/swarm/store.db',
        size_bytes: 13_002_342,
        size_label: '12.4 MB',
        created: true,
        conversation_count: 3,
        message_count: 11,
      }),
    })
  })
  await page.route('**/v1/remotes**', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'omb',
          kind: 'omb',
          label: 'OpenMousBot',
          title: 'OpenMousBot',
          host_label: '',
          base_url: 'http://127.0.0.1:8802',
          source: 'config',
        }),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        object: 'list',
        kinds: [
          { id: 'hermes', label: 'Hermes' },
          { id: 'omb', label: 'OpenMousBot' },
          { id: 'rakazo', label: 'Rakazo' },
        ],
        configured: [],
        data: [],
      }),
    })
  })
}

test('gear opens a DaisyUI modal-end settings sheet over chat', async ({ page }) => {
  const jsErrors: string[] = []
  page.on('pageerror', (e) => jsErrors.push(e.message))
  await stubApis(page)
  await page.goto('/chat')

  await expect(page.getByRole('navigation', { name: 'Primary' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Open settings' })).toBeVisible()
  await page.getByRole('button', { name: 'Open settings' }).click()

  const dialog = page.getByRole('dialog', { name: 'Settings' })
  await expect(dialog).toBeVisible()
  await expect(dialog).toHaveClass(/modal-end/)
  // DaisyUI modal-end slides in from the right; wait until the box is on-screen.
  await expect
    .poll(async () =>
      page.locator('dialog.modal-open .modal-box').evaluate((el) => el.getBoundingClientRect().x),
    )
    .toBeLessThan(1200)
  await expect(dialog).not.toHaveClass(/drawer/)

  const sections = page.getByRole('navigation', { name: 'Settings sections' })
  await expect(sections.getByRole('button', { name: 'Remotes' })).toBeVisible()
  await expect(sections.getByRole('button', { name: 'Hermes' })).toHaveCount(0)
  await expect(sections.getByRole('button', { name: 'OMB' })).toHaveCount(0)
  await expect(sections.getByRole('button', { name: 'Rakazo' })).toHaveCount(0)

  await sections.getByRole('button', { name: 'Remotes' }).click()
  await expect(dialog.getByRole('button', { name: /Add remote/i })).toBeVisible()
  await expect(dialog.getByText(/No remotes configured/i)).toBeVisible()
  // The pane copy *names* OpenMousBot as an example of an HTTP remote kind; the
  // rule under test is that unconfigured kinds are not listed as remotes
  // (REQ-59 / #322), plus the copy rule that the letters OMB never appear.
  await expect(dialog.getByText(/Only remotes you add appear here/i)).toBeVisible()
  await expect(dialog.getByText(/No remotes configured yet/i)).toBeVisible()
  await expect(dialog.getByText(/\bOMB\b/)).toHaveCount(0)
  await expect(sections.getByRole('button', { name: 'Retention' })).toBeVisible()
  await expect(sections.getByRole('button', { name: 'Hostname' })).toBeVisible()
  await expect(sections.getByRole('button', { name: 'Show LLM profiles' })).toBeVisible()
  await expect(sections.getByRole('button', { name: 'Rail' })).toBeVisible()
  await expect(sections.getByRole('button', { name: 'System' })).toBeVisible()

  await sections.getByRole('button', { name: 'Retention' }).click()
  await expect(page.getByRole('heading', { name: 'Retention' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save retention' })).toHaveCount(0)
  await expect(
    page.getByRole('link', { name: 'Server retention dashboard' }),
  ).toHaveAttribute('href', '/settings/#chat-retention-title')

  await page.getByRole('button', { name: 'Hostname' }).click()
  await page.getByRole('textbox', { name: 'Hostname override' }).fill('swarm.example.com')
  await page.getByRole('button', { name: 'Save hostname' }).click()
  await expect(page.getByText('Hostname saved')).toBeVisible()
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('swarm_hostname_override')))
    .toBe('swarm.example.com')

  await page.getByRole('button', { name: 'Rail' }).click()
  // Settings installs theme families as checkboxes (REQ-828); the theme in force
  // follows the sole installed family, so persist it by narrowing the install set.
  const themes = dialog.getByTestId('installed-avatar-themes')
  await expect(themes).toBeVisible()
  const blobsTheme = themes.getByRole('checkbox', { name: 'Blobs' })
  const beeTheme = themes.getByRole('checkbox', { name: 'Bee' })
  const blandTheme = themes.getByRole('checkbox', { name: 'Default' })
  await expect(blobsTheme).toBeChecked()
  await beeTheme.check()
  await blobsTheme.uncheck()
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('swarm_avatar_theme')))
    .toBe('bee')
  await blandTheme.check()
  await beeTheme.uncheck()
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('swarm_avatar_theme')))
    .toBe('bland')

  await page.getByRole('button', { name: 'System' }).click()
  await expect(page.getByRole('heading', { name: 'System' })).toBeVisible()
  await expect(page.getByText('12.4 MB')).toBeVisible()
  await expect(page.getByText('~/share/swarm/store.db')).toBeVisible()
  await expect(page.getByText(/local database/i)).toBeVisible()
  await expect(page.locator('#os-system-store')).not.toContainText('Django')

  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()

  expect(jsErrors, `uncaught JS errors: ${jsErrors.join(' | ')}`).toHaveLength(0)
})

test('settings sheet traps Tab inside the native dialog', async ({ page }) => {
  await stubApis(page)
  await page.goto('/chat')
  const gear = page.getByRole('button', { name: 'Open settings' })
  await gear.click()
  const dialog = page.getByRole('dialog', { name: 'Settings' })
  await expect(dialog).toBeVisible()

  for (let i = 0; i < 12; i++) {
    await page.keyboard.press('Tab')
    const inside = await page.evaluate(() => {
      const el = document.querySelector('dialog.modal-open')
      const active = document.activeElement
      return Boolean(el && active && el.contains(active))
    })
    expect(inside, `Tab ${i + 1} left the Settings dialog`).toBe(true)
  }

  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect(gear).toBeFocused()
})
