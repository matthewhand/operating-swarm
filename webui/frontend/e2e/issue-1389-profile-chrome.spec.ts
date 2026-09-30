import { mkdirSync } from 'node:fs'
import path from 'node:path'
import { expect, test, type Page } from '@playwright/test'
import { artifactsDir } from './helpers/artifacts'

/**
 * #1389 visual proof — real SPA Identity / rail / header / pack preview.
 * Secret-free fixture values only (no tokens, keys, or live credentials).
 */
const OUT_DOCS = path.resolve(process.cwd(), '../../docs/screenshots/1389-profile')
const PACK = {
  schema: 1,
  kind: 'agent_template',
  agent_id: 'codey',
  profile: {
    display_name: 'Storefront Bee',
    description: 'Short storefront blurb for the rail and pack card.',
    title: 'Guide',
    role: 'support',
    avatar_shape: 'hexagon',
    avatar_color: '#f59e0b',
    avatar_path: '/avatars/bee/bee-profile-worker.svg',
  },
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

function emptyProfile(agentId: string) {
  const profile = {
    display_name: '',
    description: '',
    title: '',
    role: '',
    avatar_shape: 'circle',
    avatar_color: '',
    avatar_path: null as string | null,
  }
  return {
    object: 'agent_profile',
    agent_id: agentId,
    ...profile,
    profile,
    pack: { schema: 1, kind: 'agent_template', agent_id: agentId, profile },
  }
}

async function stubProfileApis(page: Page) {
  const store: Record<string, ReturnType<typeof emptyProfile>> = {}

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
  await page.route('**/v1/team-rosters**', async (route) => {
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
  await page.route('**/v1/skills**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'list', data: [] }),
    })
  })
  await page.route('**/v1/cli-agents**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'cli_agents', clis: [] }),
    })
  })
  await page.route('**/v1/image-gen**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ object: 'image_gen_settings', enabled: false, avatars: {} }),
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
    const url = new URL(route.request().url())
    const agentId = url.searchParams.get('agent') || 'codey'
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        agent_id: agentId,
        conversation_id: url.searchParams.get('conversation_id') || 'conv-1389',
        messages: [],
      }),
    })
  })
  await page.route('**/v1/agents/**/profile/**', async (route) => {
    const url = route.request().url()
    const match = url.match(/\/v1\/agents\/([^/]+)\/profile/)
    const agentId = decodeURIComponent(match?.[1] || 'codey')
    const method = route.request().method().toUpperCase()
    const current = store[agentId] || emptyProfile(agentId)
    if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(current),
      })
      return
    }
    let patch: Record<string, unknown> = {}
    try {
      patch = route.request().postDataJSON() as Record<string, unknown>
    } catch {
      patch = {}
    }
    const nextProfile = {
      ...current.profile,
      ...patch,
      ...((patch.profile as Record<string, unknown> | undefined) || {}),
    }
    const next = {
      object: 'agent_profile' as const,
      agent_id: agentId,
      ...nextProfile,
      profile: nextProfile,
      pack: { schema: 1, kind: 'agent_template', agent_id: agentId, profile: nextProfile },
    }
    store[agentId] = next as ReturnType<typeof emptyProfile>
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(next),
    })
  })
  await page.route('**/v1/agents/**/settings/**', async (route) => {
    const url = route.request().url()
    const match = url.match(/\/v1\/agents\/([^/]+)\/settings/)
    const agentId = decodeURIComponent(match?.[1] || 'codey')
    const profile = (store[agentId] || emptyProfile(agentId)).profile
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        object: 'agent_settings',
        agent_id: agentId,
        new_chat_per_task: false,
        use_suggestions: false,
        ...profile,
        profile,
      }),
    })
  })
}

async function saveShot(page: Page, name: string, locator?: ReturnType<Page['locator']>) {
  mkdirSync(OUT_DOCS, { recursive: true })
  const artifacts = artifactsDir()
  const file = `${name}.png`
  const target = locator ?? page.locator('body')
  const docsPath = path.join(OUT_DOCS, file)
  const artPath = path.join(artifacts, file)
  await target.screenshot({ path: docsPath })
  await target.screenshot({ path: artPath })
}

test('1389 product screenshots: identity, rail, header, pack preview', async ({ page }) => {
  test.setTimeout(60_000)
  await page.setViewportSize({ width: 1440, height: 900 })
  // Laptop default is the 118px one-column detent; persist the labeled rail
  // so Honey Bee is readable instead of an avatar-only crop.
  await page.addInitScript(() => {
    localStorage.setItem('swarm_rail_width', '256')
  })
  await stubProfileApis(page)
  await page.goto('/chat?blueprint=codey')

  const rail = page.getByRole('navigation', { name: 'Agent list' })
  await expect(rail.getByRole('link', { name: /Codey/ })).toBeVisible()
  await rail.getByRole('link', { name: /Codey/ }).click()
  await expect(page.getByTestId('selected-agent-header')).toBeVisible()

  const generations = page.getByTestId('generations-panel')
  if (await generations.isVisible().catch(() => false)) {
    await page.getByRole('button', { name: 'Close generations panel' }).click()
    await expect(generations).toHaveCount(0)
  }

  await page.evaluate(() => {
    window.dispatchEvent(
      new CustomEvent('swarm:open-agent-editor', { detail: { agentId: 'codey' } }),
    )
  })
  const editor = page.locator('#os-agent-editor')
  await expect(editor).toBeVisible()
  await expect(editor.getByLabel('Name')).toBeVisible()

  await editor.getByLabel('Name').fill('Honey Bee')
  await editor.getByLabel('Description').fill('Short storefront blurb')
  await editor.getByLabel('Title').fill('Guide')
  await editor.getByLabel('Avatar shape').selectOption('hexagon')
  await editor.locator('input[name="agent-avatar-color"]').fill('#f59e0b')

  await expect(editor.getByLabel('Name')).toHaveValue('Honey Bee')
  await expect(editor.getByTestId('agent-profile-preview-name').first()).toHaveText('Honey Bee')
  await expect(editor.getByTestId('agent-editor-profile-chrome')).toBeVisible()

  await saveShot(page, '1389-identity-edit', page.locator('#agent-editor-panel-identity'))

  const packPanel = editor.getByTestId('agent-template-pack-panel')
  await packPanel.scrollIntoViewIfNeeded()
  await editor.getByLabel('Pack JSON').fill(JSON.stringify(PACK, null, 2))
  await editor.getByLabel('Pack JSON').blur()
  await expect(editor.getByTestId('agent-template-import-preview')).toBeVisible()
  await expect(editor.getByTestId('agent-template-import-preview')).toContainText('Storefront Bee')
  await saveShot(page, '1389-pack-preview', packPanel)

  await page.getByRole('dialog', { name: /Edit / }).getByTestId('sidepane-conceal').click()
  await expect(page.locator('#os-agent-editor')).toBeHidden()

  const honeyName = page.getByTestId('rail-agent-name').filter({ hasText: 'Honey Bee' })
  await expect(honeyName).toBeVisible()
  await expect(page.getByTestId('os-agent-rail')).toHaveAttribute('data-avatar-only', 'false')
  await expect(page.getByTestId('os-identity-name')).toHaveText('Honey Bee')
  await expect(page.getByTestId('os-header-profile-title')).toHaveText('Guide')

  const honeyRow = page.locator('.os-agent-row').filter({ has: honeyName })
  await honeyRow.scrollIntoViewIfNeeded()
  await saveShot(page, '1389-rail-profile', honeyRow)
  await saveShot(page, '1389-header-profile', page.getByTestId('selected-agent-header'))
})
