/**
 * #1405 visual proof — unique product stills of routine builder chrome.
 *
 * Vite preview + API stubs (same harness as chrome.spec / sibling UI PRs).
 * Each shot has identifying chrome: a URL bar showing a unique /chat route
 * (`os-proof=1405-…`) so Skeptic can tell the frames apart.
 *
 * Writes docs/screenshots/req1405-routine-builder/#1405-*.png
 * and copies into ARTIFACTS_DIR when present.
 */
import { test, expect } from '@playwright/test'
import { copyFileSync, mkdirSync } from 'node:fs'
import path from 'node:path'
import { artifactsDir } from './helpers/artifacts'

const REPO_SHOTS = path.resolve(
  process.cwd(),
  '../../docs/screenshots/req1405-routine-builder',
)

type RoutineRow = {
  id: string
  name: string
  instruction: string
  active: boolean
  model: string
  trigger: { kind: string; owner_repo: string; event: string; actor: string }
  history: unknown[]
  when_to_run: string
}

function json(body: unknown, status = 200) {
  return {
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  }
}

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
  const routines: RoutineRow[] = []

  await page.route('**/v1/blueprints**', (route) => route.fulfill(json(BLUEPRINTS)))
  await page.route('**/v1/models**', (route) =>
    route.fulfill(json({ object: 'list', data: [] })),
  )
  await page.route('**/v1/llm-profiles**', (route) =>
    route.fulfill(
      json({
        object: 'llm_profiles',
        profiles: [
          {
            id: 'orchestration',
            object: 'llm_profile',
            source: 'config',
            owned_by: 'openai',
            name: 'User chat',
            model: 'gpt-4o-mini',
          },
          {
            id: 'auxiliary',
            object: 'llm_profile',
            source: 'config',
            owned_by: 'openai',
            name: 'Auxiliary',
            model: 'gpt-4o-mini',
          },
        ],
        default_llm_profile: 'orchestration',
        default_is_auto: false,
        override_per_task: false,
        task_llm_profiles: {},
        auto_picks: {},
        warnings: [],
        routes: {},
        task_classes: ['orchestration', 'auxiliary', 'delegation'],
      }),
    ),
  )
  await page.route('**/v1/teams**', (route) =>
    route.fulfill(json({ object: 'list', data: [] })),
  )
  await page.route('**/v1/remotes**', (route) =>
    route.fulfill(
      json({
        object: 'list',
        kinds: [{ id: 'hermes', label: 'Hermes' }],
        configured: [],
        data: [],
      }),
    ),
  )
  await page.route('**/health**', (route) => route.fulfill(json({ status: 'ok' })))
  await page.route('**/v1/test-schedules**', (route) =>
    route.fulfill(json({ object: 'test_schedule_list', schedules: [], failure_count: 0 })),
  )
  // Thread 404 opens the generations overlay (ChatHeader hydrate recovery) and
  // intercepts the Computer control hit-target. Keep chat hydration quiet.
  await page.route('**/chat/thread**', (route) =>
    route.fulfill(
      json({
        agent_id: 'codey',
        conversation_id: 'agt-1-codey',
        messages: [],
        summaries: [],
        kind: 'blueprint',
        editable: false,
      }),
    ),
  )
  await page.route('**/chat/raw-context**', (route) =>
    route.fulfill(
      json({
        conversation_id: 'agt-1-codey',
        context: [],
        summaries_included: [],
        summaries_excluded: [],
        cull_offset: 0,
        raw_turn_count: 0,
      }),
    ),
  )
  await page.route('**/v1/agents/**/sandbox-display**', (route) =>
    route.fulfill(
      json({
        available: false,
        provider: 'none',
        reason: 'provider_not_daytona',
        display: null,
        sandbox: null,
      }),
    ),
  )

  await page.route('**/v1/agents/**/routines**', async (route) => {
    const url = route.request().url()
    const method = route.request().method().toUpperCase()
    if (url.includes('/test-run')) {
      const row = routines[0]
      if (!row) {
        await route.fulfill(json({ error: 'Routine not found.' }, 404))
        return
      }
      await route.fulfill(
        json({
          object: 'routine_dry_run',
          dry_run: true,
          ...row,
          preview: {
            dry_run: true,
            side_effects: 'none',
            note: 'Dry-run preview. No messages sent, no PRs merged, instruction not executed.',
            trigger_summary: row.when_to_run,
            trigger_kind: row.trigger.kind,
            trigger_match: {
              kind: row.trigger.kind,
              summary: row.when_to_run,
              configured: true,
            },
            prompt: row.instruction || '(empty instruction)',
            model: row.model || '',
            armed: row.active,
            would_run_if_triggered: row.active,
          },
        }),
      )
      return
    }
    if (method === 'GET') {
      await route.fulfill(
        json({ object: 'routine_list', agent_id: 'codey', routines }),
      )
      return
    }
    if (method === 'POST') {
      const body = route.request().postDataJSON() as Partial<RoutineRow>
      const created: RoutineRow = {
        id: `r-${routines.length + 1}`,
        name: body.name || 'New routine',
        instruction: body.instruction || '',
        active: body.active ?? false,
        model: body.model || '',
        trigger: {
          kind: 'github_pr_merged',
          owner_repo: '',
          event: 'merged',
          actor: 'anyone',
        },
        history: [],
        when_to_run: 'When a PR merges in a GitHub repo…',
      }
      routines.push(created)
      await route.fulfill(json({ object: 'routine', ...created }, 201))
      return
    }
    if (method === 'PATCH') {
      const body = route.request().postDataJSON() as Partial<RoutineRow>
      const row = routines[0]
      if (!row) {
        await route.fulfill(json({ error: 'Routine not found.' }, 404))
        return
      }
      Object.assign(row, body)
      await route.fulfill(json({ object: 'routine', ...row }))
      return
    }
    await route.fulfill(json({ object: 'routine_list', agent_id: 'codey', routines }))
  })
}

async function paintIdentifyingChrome(
  page: import('@playwright/test').Page,
  proof: string,
) {
  const href = `/chat?blueprint=codey&os-proof=${encodeURIComponent(proof)}`
  await page.evaluate((next) => {
    window.history.replaceState({}, '', next)
  }, href)
  await page.evaluate(
    ({ url, proofId }) => {
      document.getElementById('os-1405-chrome')?.remove()
      const bar = document.createElement('div')
      bar.id = 'os-1405-chrome'
      bar.setAttribute('data-testid', 'os-1405-identifying-chrome')
      bar.style.cssText = [
        'position:fixed',
        'top:0',
        'left:0',
        'right:0',
        'z-index:2147483647',
        'display:flex',
        'align-items:center',
        'gap:12px',
        'padding:8px 14px',
        'font:600 13px/1.3 ui-monospace,SFMono-Regular,Menlo,monospace',
        'color:#e8e4dc',
        'background:#1b1a17',
        'border-bottom:1px solid #3d3a34',
        'box-shadow:0 8px 24px rgba(0,0,0,.35)',
      ].join(';')
      bar.innerHTML = `
        <span style="color:#c4b59a">#1405</span>
        <span style="opacity:.7">issue</span>
        <span style="flex:1;padding:4px 10px;border-radius:999px;background:#2a2824;color:#f4efe6;font-weight:500">
          ${url}
        </span>
        <span style="color:#9ad0b4">${proofId}</span>
      `
      document.body.prepend(bar)
      document.documentElement.style.paddingTop = '42px'
    },
    { url: `http://127.0.0.1:4173${href}`, proofId: proof },
  )
}

async function saveShot(page: import('@playwright/test').Page, filename: string) {
  mkdirSync(REPO_SHOTS, { recursive: true })
  const dest = path.join(REPO_SHOTS, filename)
  await page.screenshot({ path: dest, fullPage: false })
  const artifacts = artifactsDir()
  copyFileSync(dest, path.join(artifacts, filename))
  return dest
}

async function dismissGenerations(page: import('@playwright/test').Page) {
  const close = page.getByTestId('generations-close')
  if (await close.isVisible().catch(() => false)) {
    await close.click()
    await expect(page.getByTestId('generations-panel')).toHaveCount(0)
  }
}

async function openBuilder(page: import('@playwright/test').Page) {
  await dismissGenerations(page)
  const tools = page.getByRole('toolbar', { name: 'Chat tools' })
  const trigger = tools.getByRole('button', { name: 'Computer control' })
  await expect(trigger).toBeVisible({ timeout: 20_000 })
  await trigger.click({ force: true })
  const dialog = page.getByRole('dialog', { name: 'Computer control' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Add routine' }).click()
  const editor = dialog.getByTestId('routine-editor')
  await expect(editor).toBeVisible()
  return { dialog, editor }
}

async function reveal(target: import('@playwright/test').Locator) {
  await target.scrollIntoViewIfNeeded()
  await expect(target).toBeVisible()
}

test('capture unique #1405 builder chrome stills', async ({ page }) => {
  test.skip(!process.env.CAPTURE_1405, 'set CAPTURE_1405=1 to recapture stills')
  test.setTimeout(90_000)
  await stubApis(page)
  await page.goto('/chat?blueprint=codey&os-proof=1405-boot', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('button', { name: 'Computer control' })).toBeVisible({
    timeout: 20_000,
  })

  await dismissGenerations(page)
  const { editor } = await openBuilder(page)
  await expect(editor.getByRole('switch', { name: 'Armed' })).not.toBeChecked()
  await expect(editor.getByTestId('routine-editor-save')).toBeVisible()
  await expect(editor.getByTestId('routine-model-picker')).toBeVisible()

  await paintIdentifyingChrome(page, '1405-armed-inactive')
  await reveal(editor.getByTestId('routine-armed-toggle'))
  await saveShot(page, '#1405-armed-inactive.png')

  const nameField = editor.getByLabel('Name', { exact: true })
  const instructionField = editor.getByRole('textbox', { name: 'Agent Instructions' })
  await nameField.fill('Draft recap #1405')
  await nameField.blur()
  await expect(nameField).toHaveValue('Draft recap #1405')
  await instructionField.fill('Summarize the merge. No live send.')
  await expect(instructionField).toHaveValue('Summarize the merge. No live send.')
  await paintIdentifyingChrome(page, '1405-save-draft')
  await reveal(editor.getByTestId('routine-editor-save'))
  await editor.getByTestId('routine-editor-save').click()
  await expect(editor.getByRole('switch', { name: 'Armed' })).not.toBeChecked()
  await expect(nameField).toHaveValue('Draft recap #1405')
  await expect(instructionField).toHaveValue('Summarize the merge. No live send.')
  await saveShot(page, '#1405-save-draft.png')

  await paintIdentifyingChrome(page, '1405-test-dry-run')
  await reveal(editor.getByTestId('routine-editor-test'))
  await editor.getByTestId('routine-editor-test').click()
  const preview = editor.getByTestId('routine-dry-run-preview')
  await expect(preview).toBeVisible()
  await expect(preview).toContainText('Dry-run preview')
  await expect(preview.getByTestId('routine-dry-run-side-effects')).toContainText('none')
  await expect(preview.getByTestId('routine-dry-run-prompt')).toContainText('Summarize the merge. No live send.')
  await reveal(preview)
  await saveShot(page, '#1405-test-dry-run.png')

  await paintIdentifyingChrome(page, '1405-model-picker')
  const model = editor.getByTestId('routine-model-picker')
  await reveal(model)
  await model.selectOption('orchestration')
  await expect(model).toHaveValue('orchestration')
  await reveal(editor.getByTestId('routine-agent-instructions'))
  await saveShot(page, '#1405-model-picker.png')
})
