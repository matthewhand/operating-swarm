/**
 * #1402 — unique product screenshots of the GitHub trigger composer chips.
 *
 * Playwright + Vite preview (same harness as the other UI specs). Each shot
 * is a full product frame with identifying chrome: a URL bar showing the
 * live `/chat?blueprint=codey#1402-…` route. Writes PNGs named `#1402-*`
 * under docs/screenshots/ for Skeptic review.
 *
 *   npx playwright test e2e/github-trigger-composer-1402.spec.ts
 */
import path from 'node:path'
import { mkdirSync, copyFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'
import { artifactsDir } from './helpers/artifacts'

const SHOT_DIR = path.resolve(process.cwd(), '../../docs/screenshots')

const BLUEPRINTS = {
  object: 'list',
  data: [
    {
      id: 'codey',
      object: 'blueprint',
      name: 'Codey',
      description: 'Code assistant',
      installed: true,
      compiled: true,
      rail: true,
    },
  ],
}

const SEEDED = [
  {
    id: 'r-issue-comment',
    name: 'Issue comments',
    instruction: 'Reply to the issue comment.',
    active: true,
    agent_id: 'codey',
    trigger: {
      kind: 'github_event',
      event_type: 'issue_comment.created',
      owner_repo: 'acme/widgets',
      filters: { object_kind: 'issue' },
    },
    history: [],
    when_to_run: 'When issue_comment.created in acme/widgets (on issue)…',
  },
  {
    id: 'r-issue-assigned',
    name: 'Issue assigned',
    instruction: 'Pick up the assigned issue.',
    active: true,
    agent_id: 'codey',
    trigger: {
      kind: 'github_event',
      event_type: 'issues.assigned',
      owner_repo: 'acme/widgets',
      filters: { object_kind: 'issue', actor: 'mona' },
    },
    history: [],
    when_to_run: 'When issues.assigned in acme/widgets (on issue; from mona)…',
  },
  {
    id: 'r-pr-comment',
    name: 'PR comments',
    instruction: 'Reply on the pull request.',
    active: true,
    agent_id: 'codey',
    trigger: {
      kind: 'github_event',
      event_type: 'issue_comment.created',
      owner_repo: 'acme/widgets',
      filters: { object_kind: 'pull_request' },
    },
    history: [],
    when_to_run: 'When issue_comment.created in acme/widgets (on pull_request)…',
  },
]

async function stubApis(page: import('@playwright/test').Page) {
  await page.route('**/v1/blueprints**', async (route) => {
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
  await page.route('**/v1/llm-profiles**', async (route) => {
    await route.fulfill({
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
    })
  })
  await page.route('**/v1/teams**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'list', data: [] }),
    })
  })
  await page.route('**/v1/remotes**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'list', kinds: [], configured: [], data: [] }),
    })
  })
  await page.route('**/health**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok' }),
    })
  })
  await page.route('**/chat/thread/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        agent_id: 'codey',
        conversation_id: 'conv-1402',
        messages: [{ role: 'user', content: '#1402 GitHub trigger composer fixture' }],
      }),
    })
  })
  await page.route('**/v1/test-schedules/status/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ failure_count: 0 }),
    })
  })
  await page.route('**/v1/agents/**/sandbox-display/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        provider: 'none',
        display: null,
        reason: 'provider_not_daytona',
        available: false,
      }),
    })
  })
  await page.route('**/v1/agents/**/routines**', async (route) => {
    const method = route.request().method()
    if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ object: 'routine_list', agent_id: 'codey', routines: SEEDED }),
      })
      return
    }
    if (method === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          object: 'routine',
          id: 'r-new',
          name: 'New routine',
          instruction: '',
          active: true,
          agent_id: 'codey',
          trigger: { kind: 'github_pr_merged', owner_repo: '', event: 'merged', actor: 'anyone' },
          history: [],
          when_to_run: 'When a PR merges in a GitHub repo…',
        }),
      })
      return
    }
    if (method === 'PATCH') {
      const body = route.request().postDataJSON() as Record<string, unknown>
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          object: 'routine',
          id: 'r-new',
          name: 'New routine',
          instruction: '',
          active: true,
          agent_id: 'codey',
          trigger: body.trigger ?? {
            kind: 'github_event',
            event_type: 'issues.opened',
            owner_repo: '',
            filters: {},
          },
          history: [],
        }),
      })
      return
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })
}

async function injectUrlBar(page: import('@playwright/test').Page, hash: string) {
  await page.evaluate((nextHash) => {
    if (window.location.hash !== nextHash) {
      window.location.hash = nextHash
    }
    let bar = document.getElementById('os-capture-urlbar')
    if (!bar) {
      bar = document.createElement('div')
      bar.id = 'os-capture-urlbar'
      bar.setAttribute('data-testid', 'os-capture-urlbar')
      bar.setAttribute('role', 'banner')
      document.body.prepend(bar)
    }
    bar.innerHTML = `
      <span aria-hidden="true">🔒</span>
      <span data-testid="os-capture-url">${window.location.href}</span>
    `
    Object.assign(bar.style, {
      position: 'fixed',
      top: '0',
      left: '0',
      right: '0',
      zIndex: '2147483647',
      display: 'flex',
      alignItems: 'center',
      gap: '0.5rem',
      height: '2.25rem',
      padding: '0 0.75rem',
      background: 'color-mix(in srgb, var(--color-base-200, #1e1e1e) 92%, #000)',
      color: 'var(--color-base-content, #e8e8e8)',
      borderBottom: '1px solid color-mix(in srgb, currentColor 18%, transparent)',
      font: '12px/1.2 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
    })
    document.documentElement.style.scrollPaddingTop = '2.25rem'
  }, hash)
}

async function openRoutinesEditor(page: import('@playwright/test').Page) {
  const generations = page.getByTestId('generations-panel')
  if (await generations.isVisible().catch(() => false)) {
    await generations.getByRole('button', { name: /close/i }).click()
    await expect(generations).toHaveCount(0)
  }
  await page.getByRole('button', { name: 'Computer control' }).click()
  const dialog = page.getByRole('dialog', { name: 'Computer control' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('heading', { name: 'Routines' })).toBeVisible()
  return dialog
}

async function captureShot(
  page: import('@playwright/test').Page,
  stem: string,
) {
  const composer = page.getByTestId('github-trigger-composer')
  await expect(composer).toBeVisible()
  await composer.scrollIntoViewIfNeeded()
  await expect(page.getByTestId('os-capture-urlbar')).toBeVisible()
  await expect(page.getByTestId('os-capture-url')).toContainText(stem)

  mkdirSync(SHOT_DIR, { recursive: true })
  const dest = path.join(SHOT_DIR, `${stem}.png`)
  await page.screenshot({ path: dest, fullPage: false })
  const artifact = path.join(artifactsDir(), `${stem}.png`)
  copyFileSync(dest, artifact)
  return dest
}

test.describe('GitHub trigger composer product shots (#1402)', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test('captures unique chip rows with identifying URL chrome', async ({ page }) => {
    test.setTimeout(60_000)
    await stubApis(page)
    await page.goto('/chat?blueprint=codey')
    await expect(page.getByRole('heading', { name: 'Codey' })).toBeVisible()

    const dialog = await openRoutinesEditor(page)

    const cases = [
      { name: 'Issue comments', stem: '#1402-issue-comment', event: 'Comment', object: 'Issue' },
      { name: 'Issue assigned', stem: '#1402-issue-assigned', event: 'Assigned', object: 'Issue' },
      { name: 'PR comments', stem: '#1402-pr-comment', event: 'Comment', object: 'Pull request' },
    ] as const

    for (const shot of cases) {
      await dialog.getByRole('button', { name: new RegExp(shot.name) }).click()
      await expect(dialog.getByTestId('routine-editor')).toBeVisible()
      await expect(dialog.getByTestId('github-trigger-event')).toHaveValue(
        shot.event === 'Assigned' ? 'assigned' : 'comment',
      )
      await expect(dialog.getByTestId('github-trigger-object')).toHaveValue(
        shot.object === 'Pull request' ? 'pull_request' : 'issue',
      )
      await expect(dialog.getByTestId('github-trigger-repo')).toHaveValue('acme/widgets')
      await injectUrlBar(page, shot.stem)
      await captureShot(page, shot.stem)
      await dialog.getByRole('button', { name: 'Back' }).click()
      await expect(dialog.getByRole('heading', { name: 'Routines' })).toBeVisible()
    }

    await dialog.getByRole('button', { name: 'Add routine' }).click()
    await expect(dialog.getByTestId('routine-editor')).toBeVisible()
    await dialog.getByLabel('Trigger', { exact: true }).selectOption('github_event')
    await expect(dialog.getByTestId('github-trigger-unsupported')).toBeVisible()
    await injectUrlBar(page, '#1402-missing-repo')
    await captureShot(page, '#1402-missing-repo')
  })
})
