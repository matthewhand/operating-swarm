import { test, expect } from '@playwright/test'

const REQ42_INJECTED_FIXTURE = 'REQ42_INJECTED_FIXTURE_MARKER'

const BLUEPRINTS = {
  object: 'list',
  data: [
    {
      id: 'codey',
      object: 'blueprint',
      name: 'Codey',
      description: 'Code assistant',
      abbreviation: null,
      required_mcp_servers: [],
      tags: [],
      installed: true,
      compiled: true,
      rail: true,
    },
  ],
}

async function stubApis(page: import('@playwright/test').Page) {
  // One handler for both definition endpoints: separate routes for
  // `.../summarize` and the catch-all let the catch-all win and answer the
  // summarize POST with the definition context, which silently blanked the
  // summary (no `configured` key → the pane renders its placeholder).
  await page.route('**/v1/definitions/**', async (route) => {
    if (route.request().url().includes('/summarize')) {
      const post = route.request().postDataJSON() as { source?: string; extra?: string }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          kind: 'role',
          id: 'support',
          configured: true,
          model: 'stub-llm',
          summary: `LLM summary includes ${post?.extra || REQ42_INJECTED_FIXTURE} source=${post?.source || ''}`,
        }),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        kind: 'role',
        id: 'support',
        title: 'Support',
        role: 'support',
        explanation: 'Support is Socratic.',
        source: 'ORIGINAL_SUPPORT_SOURCE',
        injected: {
          system_prompt: 'Socratic',
          tools: {},
          metadata: {},
          handoff: '',
          extra: REQ42_INJECTED_FIXTURE,
        },
        default_llm: { configured: true, model: 'stub-llm' },
      }),
    })
  })
  await page.route('**/v1/blueprints**', async (route) => {
    const url = route.request().url()
    if (url.includes('/source')) {
      const post = route.request().postDataJSON() as { content?: string } | null
      const content =
        route.request().method() === 'PUT' && post?.content
          ? post.content
          : 'ORIGINAL_SUPPORT_SOURCE'
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'support',
          files: [{ name: 'blueprint_support.py', path: 'blueprint_support.py' }],
          primary: 'blueprint_support.py',
          selected: 'blueprint_support.py',
          content,
          editable: true,
          origin: 'custom',
          readonly_reason: null,
        }),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(BLUEPRINTS),
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

test('role badge opens the explained definition pane with stub LLM summary', async ({ page }) => {
  await stubApis(page)
  await page.addInitScript(() => {
    window.localStorage.setItem('swarm_hidden_agents', JSON.stringify([]))
  })
  await page.goto('/')

  // Support is the seeded favourite tile, so both the row and its settings
  // button live in the pin grid rather than the conversation list.
  const pins = page.getByLabel('Pinned agents')
  const support = pins.getByRole('link', { name: /Support/ })
  await expect(support).toBeVisible()
  await support.getByRole('button', { name: 'Open support settings' }).click()

  const sheet = page.getByRole('dialog', { name: 'Settings' })
  await expect(sheet).toBeVisible()
  await expect(sheet).toHaveClass(/modal-end/)
  await expect(sheet.getByRole('button', { name: 'Definition' })).toHaveClass(/menu-active/)
  const pane = sheet.locator('#os-definition-pane')
  await expect(pane).toHaveAttribute('data-definition-id', 'support')
  await expect(sheet.getByTestId('definition-explanation')).toContainText('Socratic')
  await expect(sheet.getByTestId('definition-summary')).toContainText(REQ42_INJECTED_FIXTURE)

  await sheet.getByRole('button', { name: /Edit code/ }).click()
  await sheet.getByLabel('Definition source').fill('UPDATED_SUPPORT_SOURCE')
  await sheet.getByRole('button', { name: /^Save$/ }).click()
  await sheet.getByRole('button', { name: /Re-summarise/ }).click()
  await expect(sheet.getByTestId('definition-summary')).toContainText('UPDATED_SUPPORT_SOURCE')
})
