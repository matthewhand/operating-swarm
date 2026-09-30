/**
 * Settings deep-links (#674 / REQ-868): `/chat?settings=<section>` must open the
 * Settings sheet straight onto that pane on a cold load, then strip the query
 * param so a reload does not re-open it.
 *
 * This is a regression guard for the ChatPage → App dispatch timing (the child
 * effect defers one macrotask so the App listener exists before it fires) and
 * for the section allowlist in components/settings/kernel.ts.
 */
import { test, expect } from '@playwright/test'

const EMPTY_LIST = { object: 'list', data: [] }

async function stubApis(page: import('@playwright/test').Page) {
  await page.route('**/v1/blueprints**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(EMPTY_LIST),
    }),
  )
  await page.route('**/v1/models**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(EMPTY_LIST),
    }),
  )
  await page.route('**/v1/teams**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(EMPTY_LIST),
    }),
  )
  await page.route('**/v1/cli-agents/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        clis: [],
        installed: [],
        configured: [],
        discovered: [],
        native_consensus: {},
        catalog: {},
      }),
    }),
  )
  await page.route('**/v1/remotes**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'list', kinds: [], configured: [], data: [] }),
    }),
  )
  await page.route('**/v1/llm-profiles**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        object: 'llm_profiles',
        profiles: [],
        default_llm_profile: 'default',
        default_is_auto: true,
        override_per_task: false,
        task_llm_profiles: {},
        auto_picks: { default: 'default' },
        warnings: [],
        routes: {},
        task_classes: ['orchestration', 'auxiliary', 'delegation'],
      }),
    }),
  )
  await page.route('**/health**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok' }),
    }),
  )
  await page.route('**/chat/thread**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        agent_id: 'support',
        conversation_id: 'deeplink-e2e',
        messages: [],
        summaries: [],
      }),
    }),
  )
}

test('`/chat?settings=providers` opens the Providers pane and strips the param', async ({
  page,
}) => {
  await stubApis(page)
  await page.goto('/chat?settings=providers')

  const dialog = page.getByRole('dialog', { name: 'Settings' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByTestId('providers-pane')).toBeVisible()
  await expect(dialog.getByRole('heading', { name: 'Providers' })).toBeVisible()

  // The param is consumed on open (replace, not push) so it never sticks.
  // (The Support default then adds `?blueprint=support`, which is unrelated.)
  await expect(page).not.toHaveURL(/[?&]settings=/)
})

test('`/chat?settings=cli-agents` lands on the CLI agents pane', async ({ page }) => {
  await stubApis(page)
  await page.goto('/chat?settings=cli-agents')

  const dialog = page.getByRole('dialog', { name: 'Settings' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('heading', { name: 'CLI agents' })).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'CLI agents' })).toHaveAttribute(
    'aria-current',
    'page',
  )
  await expect(page).not.toHaveURL(/[?&]settings=/)
})
