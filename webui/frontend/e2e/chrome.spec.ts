import { test, expect } from '@playwright/test'

/**
 * Support ships as the seeded favourite tile (`DEFAULT_PINNED_SUPPORT`), and a
 * pinned agent is *moved* out of the conversation list (REQ-94), so Support
 * renders in the pin grid rather than inside `navigation "Agent list"`.
 */
function pinGrid(page: import('@playwright/test').Page) {
  return page.getByLabel('Pinned agents')
}

/**
 * Hidden Bots no longer opens a "Hidden agents" dialog: it opens the command
 * palette in its hidden-only mode, where each row carries an Unhide button.
 */
function hiddenPalette(page: import('@playwright/test').Page) {
  return page.getByRole('dialog', { name: 'Search' })
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
    {
      id: 'stewie',
      object: 'blueprint',
      name: 'Stewie',
      description: 'Helpful agent',
      abbreviation: null,
      required_mcp_servers: [],
      tags: [],
      installed: true,
      compiled: true,
      rail: true,
    },
  ],
}

async function stubAgentApis(page: import('@playwright/test').Page) {
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
  await page.route('**/health**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok' }),
    })
  })
  await page.route('**/v1/agents/**/routines**', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ object: 'routine_list', agent_id: 'codey', routines: [] }),
      })
      return
    }
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({
        object: 'routine',
        id: 'r-e2e',
        name: 'New routine',
        instruction: '',
        active: true,
        trigger: { kind: 'github_pr_merged', owner_repo: '', event: 'merged', actor: 'anyone' },
        history: [],
        when_to_run: 'When a PR merges in a GitHub repo…',
      }),
    })
  })
}

test('Grok chrome is left rail + chat, not a top-nav product shell', async ({ page }) => {
  const jsErrors: string[] = []
  page.on('pageerror', (e) => jsErrors.push(e.message))
  await stubAgentApis(page)
  await page.goto('/')

  const rail = page.getByRole('navigation', { name: 'Agent list' })
  await expect(pinGrid(page).getByRole('link', { name: /Support/ })).toBeVisible()
  await expect(rail.getByRole('link', { name: /Codey/ })).toBeVisible()
  // Scope hidden-agent assertions by id: the seeded demo teams include a
  // "Demo SDLC Skeptic Loop" whose row name also matches /Skeptic/.
  await expect(rail.locator('a[data-agent-id="gate"]')).toHaveCount(0)
  await expect(rail.locator('a[data-agent-id="skeptic"]')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Hidden Bots 2' })).toBeVisible()
  await expect(page.getByLabel('Pinned agents')).toBeVisible()
  await expect(page.getByRole('button', { name: /Plugins/i })).toBeVisible()
  await expect(page.getByLabel('Hostname')).toBeVisible()

  await expect(page.getByRole('navigation', { name: 'Primary' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: /^Home$/ })).toHaveCount(0)
  await expect(page.getByRole('link', { name: /^Chat$/ })).toHaveCount(0)

  await expect(page.getByRole('heading', { name: 'Support' })).toBeVisible()
  await expect(page.getByRole('textbox', { name: 'Chat message' })).toHaveAttribute(
    'placeholder',
    'Message …',
  )
  // "Add agent" in the rail also matches /Add/, so scope to the composer dock.
  await expect(page.getByTestId('chat-bottom-dock').getByRole('button', { name: 'Add' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Voice input' })).toBeVisible()
  await expect(page.getByRole('button', { name: /^Switch to (light|dark) theme$/ })).toBeVisible()
  await expect(page.getByText(/^Connected$/)).toHaveCount(0)

  const root = page.locator('[data-theme]').first()
  await expect(root).toHaveAttribute('data-theme', 'dark')
  expect(jsErrors, `uncaught JS errors: ${jsErrors.join(' | ')}`).toHaveLength(0)
})

test('left-rail Search opens the command palette overlay, not an in-place filter', async ({
  page,
}) => {
  await stubAgentApis(page)
  await page.goto('/chat')

  const list = page.getByRole('navigation', { name: 'Agent list' })
  await expect(list.getByRole('link', { name: /Codey/ })).toBeVisible()
  await expect(list.getByRole('link', { name: /Stewie/ })).toBeVisible()

  await page.getByRole('button', { name: 'Search' }).click()
  const palette = page.getByRole('dialog', { name: 'Search' })
  await expect(palette).toBeVisible()
  await expect(palette.getByRole('combobox', { name: 'Search' })).toHaveAttribute(
    'placeholder',
    'Search',
  )
  await expect(palette.getByRole('tab', { name: 'All' })).toHaveAttribute('aria-selected', 'true')
  for (const tab of ['Messages', 'Agents', 'Teams', 'Files', 'Links', 'Routines', 'Actions']) {
    await expect(palette.getByRole('tab', { name: tab })).toBeVisible()
  }
  await expect(list.getByRole('link', { name: /Codey/ })).toBeVisible()
  await expect(list.getByRole('link', { name: /Stewie/ })).toBeVisible()

  await page.keyboard.press('Escape')
  await expect(palette).toHaveCount(0)
})

test('/agents is Agent Router (not redirected to /chat)', async ({ page }) => {
  const jsErrors: string[] = []
  page.on('pageerror', (e) => jsErrors.push(e.message))
  await stubAgentApis(page)
  await page.goto('/agents')
  await expect(page).toHaveURL(/\/agents\/?$/)
  await expect(page.getByRole('textbox', { name: 'Chat message' })).toHaveCount(0)
  await expect(page.getByRole('navigation', { name: 'Primary' })).toHaveCount(0)
  expect(jsErrors, `uncaught JS errors: ${jsErrors.join(' | ')}`).toHaveLength(0)
})

test('chat header Computer control icon opens thumbnail + Routines pane (REQ-80)', async ({ page }) => {
  const jsErrors: string[] = []
  page.on('pageerror', (e) => jsErrors.push(e.message))
  await stubAgentApis(page)
  await page.goto('/chat')

  const tools = page.getByRole('toolbar', { name: 'Chat tools' })
  const trigger = page.getByRole('button', { name: 'Computer control' })
  await expect(tools).toBeVisible()
  await expect(trigger).toBeVisible()

  await trigger.click()
  const dialog = page.getByRole('dialog', { name: 'Computer control' })
  await expect(dialog).toBeVisible()
  const thumbnail = dialog.getByTestId('agent-screen-thumbnail')
  const routines = dialog.getByRole('heading', { name: 'Routines' })
  await expect(thumbnail).toBeVisible()
  await expect(routines).toBeVisible()
  const thumbBox = await thumbnail.boundingBox()
  const headingBox = await routines.boundingBox()
  expect(thumbBox && headingBox && thumbBox.y < headingBox.y).toBeTruthy()
  await expect(dialog.getByRole('button', { name: 'Add routine' })).toBeVisible()
  await expect(dialog.getByText('No routines yet.')).toBeVisible()
  await expect(dialog.getByText(/WIP/)).toHaveCount(0)
  await expect(page.getByRole('textbox', { name: 'Chat message' })).toBeVisible()

  expect(jsErrors, `uncaught JS errors: ${jsErrors.join(' | ')}`).toHaveLength(0)
})

test('right-click hide from sidebar persists across reload; unhide restores', async ({ page }) => {
  const jsErrors: string[] = []
  page.on('pageerror', (e) => jsErrors.push(e.message))
  await stubAgentApis(page)
  await page.goto('/chat')

  const list = page.getByRole('navigation', { name: 'Agent list' })
  const codey = list.getByRole('link', { name: /Codey/ })
  await expect(codey).toBeVisible()
  await expect(list.getByRole('link', { name: /Stewie/ })).toBeVisible()

  await codey.click({ button: 'right' })
  await page.getByRole('menuitem', { name: /Hide from sidebar/i }).click()
  await expect(list.getByRole('link', { name: /Codey/ })).toHaveCount(0)
  await expect(list.getByRole('link', { name: /Stewie/ })).toBeVisible()

  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('swarm_hidden_agents')))
    .toBe(JSON.stringify(['gate', 'skeptic', 'codey']))

  await page.reload()
  await expect(list.getByRole('link', { name: /Codey/ })).toHaveCount(0)
  await expect(list.getByRole('link', { name: /Stewie/ })).toBeVisible()

  await page.getByRole('button', { name: 'Hidden Bots 3' }).click()
  const hidden = hiddenPalette(page)
  await expect(hidden).toBeVisible()
  await hidden.getByRole('button', { name: /Unhide Codey/i }).click()
  await page.keyboard.press('Escape')
  await expect(hidden).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Hidden Bots 2' })).toBeVisible()
  await expect(list.getByRole('link', { name: /Codey/ })).toBeVisible()
  expect(jsErrors, `uncaught JS errors: ${jsErrors.join(' | ')}`).toHaveLength(0)
})

async function html5Drag(
  source: import('@playwright/test').Locator,
  target: import('@playwright/test').Locator,
  phase: 'highlight' | 'drop' | 'full' = 'full',
) {
  await source.evaluate((el) => {
    el.dispatchEvent(
      new DragEvent('dragstart', { bubbles: true, cancelable: true, dataTransfer: new DataTransfer() }),
    )
  })
  if (phase === 'highlight' || phase === 'full') {
    await target.evaluate((el) => {
      const dt = new DataTransfer()
      el.dispatchEvent(new DragEvent('dragenter', { bubbles: true, cancelable: true, dataTransfer: dt }))
      el.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: dt }))
    })
  }
  if (phase === 'drop' || phase === 'full') {
    await target.evaluate((el) => {
      el.dispatchEvent(
        new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: new DataTransfer() }),
      )
    })
    // Hide unmounts the source row; dragend is best-effort.
    if ((await source.count()) > 0) {
      await source.evaluate((el) => {
        el.dispatchEvent(
          new DragEvent('dragend', { bubbles: true, cancelable: true, dataTransfer: new DataTransfer() }),
        )
      })
    }
  }
}

test('drag any rail row onto Hidden, including Support; Unhide restores; no Hide-all', async ({
  page,
}) => {
  await stubAgentApis(page)
  await page.goto('/chat')

  const list = page.getByRole('navigation', { name: 'Agent list' })
  const zone = page.getByRole('region', { name: 'Hidden Bots' })
  // REQ-26 first load already seeded gate + skeptic.
  await expect(page.getByRole('button', { name: 'Hidden Bots 2' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Hide all/i })).toHaveCount(0)

  const pins = pinGrid(page)
  const support = pins.getByRole('link', { name: /Support/ })
  await html5Drag(support, zone, 'highlight')
  await expect(zone).toHaveAttribute('data-drag-over', 'true')
  await html5Drag(support, zone, 'drop')
  await expect(pins.getByRole('link', { name: /Support/ })).toHaveCount(0)
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('swarm_hidden_agents')))
    .toBe(JSON.stringify(['gate', 'skeptic', 'support']))

  const codey = list.getByRole('link', { name: /Codey/ })
  await html5Drag(codey, zone)
  await expect(list.getByRole('link', { name: /Codey/ })).toHaveCount(0)
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('swarm_hidden_agents')))
    .toBe(JSON.stringify(['gate', 'skeptic', 'support', 'codey']))

  await expect(page.getByRole('button', { name: 'Hidden Bots 4' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Hide all/i })).toHaveCount(0)
  await page.getByRole('button', { name: 'Hidden Bots 4' }).click()
  const dialog = hiddenPalette(page)
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: /Unhide Support/i }).click()
  await dialog.getByRole('button', { name: /Unhide Codey/i }).click()
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(pins.getByRole('link', { name: /Support/ })).toBeVisible()
  await expect(list.getByRole('link', { name: /Codey/ })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Hidden Bots 2' })).toBeVisible()
})

test('first load seeds Hidden with gate and skeptic; Unhide persists', async ({ page }) => {
  await stubAgentApis(page)
  await page.goto('/')

  const list = page.getByRole('navigation', { name: 'Agent list' })
  await expect(pinGrid(page).getByRole('link', { name: /Support/ })).toBeVisible()
  await expect(list.locator('a[data-agent-id="gate"]')).toHaveCount(0)
  await expect(list.locator('a[data-agent-id="skeptic"]')).toHaveCount(0)
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('swarm_hidden_agents')))
    .toBe(JSON.stringify(['gate', 'skeptic']))

  await page.getByRole('button', { name: 'Hidden Bots 2' }).click()
  const dialog = hiddenPalette(page)
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: /Unhide Safety/i }).click()
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(list.locator('a[data-agent-id="gate"]')).toBeVisible()
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('swarm_hidden_agents')))
    .toBe(JSON.stringify(['skeptic']))

  await page.reload()
  await expect(list.locator('a[data-agent-id="gate"]')).toBeVisible()
  await expect(list.locator('a[data-agent-id="skeptic"]')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Hidden Bots 1' })).toBeVisible()
})

test('row menu opens an agent-scoped editor; Blueprint picker persists; Edit blueprint lands on the list', async ({
  page,
}) => {
  const jsErrors: string[] = []
  page.on('pageerror', (e) => jsErrors.push(e.message))
  await stubAgentApis(page)
  await page.goto('/')

  const list = page.getByRole('navigation', { name: 'Agent list' })
  // The hover pencils were deliberately removed from rail rows (#694), so the
  // agent-scoped editor is reached from the row context menu now.
  const support = pinGrid(page).getByRole('link', { name: /Support/ })
  await expect(support).toBeVisible()
  // REQ-26 seeds gate/skeptic as Hidden on first load; Support stays visible.
  await expect(list.locator('a[data-agent-id="gate"]')).toHaveCount(0)
  await expect(list.locator('a[data-agent-id="skeptic"]')).toHaveCount(0)

  await support.click({ button: 'right' })
  const edit = page.getByRole('menuitem', { name: 'Edit Profile' })
  await expect(edit).toBeVisible()
  await edit.click()

  const editor = page.getByRole('dialog', { name: /Edit / })
  await expect(editor).toBeVisible()
  await expect(editor).toHaveClass(/modal-end/)
  await expect(editor.getByRole('button', { name: 'Remotes' })).toHaveCount(0)
  await expect(editor.getByRole('button', { name: 'System' })).toHaveCount(0)
  await expect(editor.getByRole('navigation', { name: 'Settings sections' })).toHaveCount(0)
  const picker = editor.getByLabel('Blueprint')
  await expect(picker).toBeVisible()
  await picker.selectOption('codey')
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('swarm_agent_edits')))
    .toContain('"blueprintId":"codey"')

  await editor.getByRole('button', { name: /Edit blueprint/ }).click()
  const sheet = page.getByRole('dialog', { name: 'Settings' })
  await expect(sheet).toBeVisible()
  await expect(sheet.getByRole('navigation', { name: 'Settings sections' }).getByRole('button', { name: 'Blueprints' })).toHaveClass(/menu-active/)
  const blueprints = sheet.getByRole('listbox', { name: 'Blueprints' })
  await expect(blueprints.getByRole('option', { name: 'Codey' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('dialog', { name: /Teams/i })).toHaveCount(0)
  expect(jsErrors, `uncaught JS errors: ${jsErrors.join(' | ')}`).toHaveLength(0)
})

test('composer + Compact borders nested summaries and keeps leftover operator links out', async ({
  page,
}) => {
  await stubAgentApis(page)
  await page.route('**/chat/thread/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        agent_id: 'codey',
        conversation_id: 'c-e2e',
        messages: [
          { role: 'user', content: 'prior question' },
          { role: 'assistant', content: 'prior answer' },
        ],
        summaries: [],
      }),
    })
  })
  await page.route('**/chat/compact/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        summary: {
          id: 2,
          conversation_id: 'c-e2e',
          span: { start: 0, end: 1 },
          parent_summary_id: 1,
          body: 'outer digest',
          created_at: '2026-09-03T00:00:00Z',
          replaced_count: 2,
        },
        summaries: [
          {
            id: 1,
            conversation_id: 'c-e2e',
            span: { start: 0, end: 1 },
            parent_summary_id: null,
            body: 'inner digest',
            created_at: '2026-09-03T00:00:00Z',
            replaced_count: 2,
          },
          {
            id: 2,
            conversation_id: 'c-e2e',
            span: { start: 0, end: 1 },
            parent_summary_id: 1,
            body: 'outer digest',
            created_at: '2026-09-03T00:00:00Z',
            replaced_count: 2,
          },
        ],
      }),
    })
  })
  await page.goto('/chat?blueprint=codey')
  await expect(page.getByText('prior question')).toBeVisible()

  // "Add agent" in the rail also matches /Add/, so scope to the composer dock.
  await page.getByTestId('chat-bottom-dock').getByRole('button', { name: 'Add' }).click()
  await expect(page.getByRole('menuitem', { name: 'Compact' })).toBeVisible()
  await expect(page.getByRole('menuitem', { name: 'Blueprints' })).toHaveCount(0)
  await expect(page.getByRole('menuitem', { name: 'Teams' })).toHaveCount(0)
  await expect(page.getByRole('menuitem', { name: 'Settings' })).toHaveCount(0)

  await page.getByRole('menuitem', { name: 'Compact' }).click()
  const blocks = page.getByTestId('chat-summary')
  await expect(blocks).toHaveCount(2)
  await expect(blocks.first()).toHaveClass(/chat-summary/)
  await expect(page.locator('.chat-summary--nested')).toBeVisible()
  // Target the card chip: a plain getByText('Summary') also matches the
  // "Auxiliary (code summary)" option in the routing picker.
  await expect(page.getByTestId('chat-summary-chip').first()).toBeVisible()
  await expect(page.getByText('outer digest')).toBeVisible()
  await expect(page.getByText('inner digest')).toBeVisible()
  await expect(page.getByText('prior question')).toHaveCount(0)
})
