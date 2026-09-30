/**
 * #1403 visual proof — Playwright / Vite harness.
 *
 * Captures unique product frames of the Tools checkbox at
 * `/__proof__/routines-1403` with the live URL in-frame.
 */
import { test, expect } from '@playwright/test'
import { copyFileSync, mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { artifactsDir } from './helpers/artifacts'

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const DOCS_DIR = path.join(REPO_ROOT, 'docs', 'screenshots')

const SHOTS = [
  {
    file: '#1403-dialog-issue-default-on.png',
    surface: 'dialog',
    state: 'issue-on',
    checked: true,
    clickRow: false,
  },
  {
    file: '#1403-dialog-interval-default-off.png',
    surface: 'dialog',
    state: 'interval-off',
    checked: false,
    clickRow: false,
  },
  {
    file: '#1403-pane-issue-default-on.png',
    surface: 'pane',
    state: 'issue-on',
    checked: true,
    clickRow: true,
  },
  {
    file: '#1403-pane-removed-persists.png',
    surface: 'pane',
    state: 'removed',
    checked: false,
    clickRow: true,
  },
] as const

test.describe('#1403 Open PR tool defaults', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/v1/blueprints**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: [] }) }),
    )
    await page.route('**/v1/models**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: [] }) }),
    )
    await page.route('**/health**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) }),
    )
    await page.route('**/v1/agents/**/routines/**', async (route) => {
      const url = new URL(route.request().url())
      const state = url.searchParams.get('state') || new URL(page.url()).searchParams.get('state') || 'issue-on'
      const routine =
        state === 'removed'
          ? {
              id: 'r-removed-1403',
              name: 'Issue solver (Open PR removed)',
              instruction: 'Investigate the issue. Do not open a pull request.',
              active: true,
              trigger: { kind: 'github_event', event_type: 'issues.opened', owner_repo: 'owner/repo' },
              tools: [],
              tools_explicit: true,
              history: [],
              when_to_run: 'When issues.opened in owner/repo…',
            }
          : state === 'interval-off'
            ? {
                id: 'r-interval-1403',
                name: 'Hourly recap',
                instruction: 'Summarize the last hour.',
                active: true,
                trigger: { kind: 'interval', seconds: 3600 },
                tools: [],
                tools_explicit: false,
                history: [],
                when_to_run: 'Every 1 hour…',
              }
            : {
                id: 'r-issue-1403',
                name: 'GitHub Issue Solver',
                instruction: 'Investigate the issue and open a pull request.',
                active: true,
                trigger: { kind: 'github_event', event_type: 'issues.opened', owner_repo: 'owner/repo' },
                tools: ['open_pull_request'],
                tools_explicit: false,
                history: [],
                when_to_run: 'When issues.opened in owner/repo…',
              }
      if (route.request().method() === 'PATCH') {
        const patch = route.request().postDataJSON() || {}
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ object: 'routine', ...routine, ...patch }),
        })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ object: 'routine_list', agent_id: 'codey', routines: [routine] }),
      })
    })
  })

  for (const shot of SHOTS) {
    test(`captures ${shot.file}`, async ({ page }) => {
      const dest = path.join(DOCS_DIR, shot.file)
      const artifact = path.join(artifactsDir(), shot.file)
      mkdirSync(DOCS_DIR, { recursive: true })

      const url = `/__proof__/routines-1403?surface=${shot.surface}&state=${shot.state}`
      await page.goto(url)
      await expect(page.getByTestId('routine-tools-proof-1403')).toBeVisible()
      await expect(page.getByTestId('proof-url-1403')).toContainText('/__proof__/routines-1403')
      await expect(page.getByTestId('proof-url-1403')).toContainText(`surface=${shot.surface}`)
      await expect(page.getByTestId('proof-url-1403')).toContainText(`state=${shot.state}`)

      if (shot.clickRow) {
        const rowName =
          shot.state === 'removed' ? /Issue solver/ : shot.state === 'interval-off' ? /Hourly recap/ : /GitHub Issue Solver/
        await page.getByRole('button', { name: rowName }).click()
        await expect(page.getByTestId('routine-editor')).toBeVisible()
      } else {
        await expect(page.getByTestId('routine-editor-dialog')).toBeVisible()
      }

      const box = page.getByTestId('routine-tool-open-pull-request')
      await expect(box).toBeVisible()
      if (shot.checked) await expect(box).toBeChecked()
      else await expect(box).not.toBeChecked()

      await page.screenshot({ path: dest, fullPage: true })
      copyFileSync(dest, artifact)
    })
  }
})
