import { test, expect } from '@playwright/test'
import { artifactsDir } from './helpers/artifacts'

const BLUEPRINTS = {
  object: 'list',
  data: [
    {
      id: 'cli_agent',
      object: 'blueprint',
      name: 'CLI Agent',
      description: 'Single CLI',
      tags: ['cli'],
      installed: true,
      compiled: true,
      rail: true,
    },
    {
      id: 'codey',
      object: 'blueprint',
      name: 'Codey',
      description: 'Code assistant',
      tags: [],
      installed: true,
      compiled: true,
      rail: true,
    },
  ],
}

// #445: the header must keep clamping long titles without clipping the flyout.
const LONG_AGENT_NAME =
  'Extremely long operating agent title that must never widen the chat header or the page '

const LONG_BLUEPRINT = {
  id: 'cli_agent_long',
  object: 'blueprint',
  name: LONG_AGENT_NAME,
  description: 'Long title',
  tags: ['cli'],
  installed: true,
  compiled: true,
  rail: true,
}

BLUEPRINTS.data.push(LONG_BLUEPRINT)

const AGY_MODELS = [
  'gemini-3.8-flash-high',
  'gemini-3.8-flash-medium',
  'claude-sonnet-4-6',
]

const CLI_AGENTS = {
  clis: ['agy', 'grok'],
  installed: ['agy', 'grok'],
  configured: ['agy', 'grok'],
  list_models: { agy: AGY_MODELS, grok: ['grok-4.6'] },
}

async function stubApis(page: import('@playwright/test').Page) {
  await page.route('**/v1/blueprints**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(BLUEPRINTS),
    })
  })
  await page.route('**/v1/cli-agents**', async (route) => {
    const url = route.request().url()
    if (url.includes('/models')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ cli: 'agy', models: AGY_MODELS }),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(CLI_AGENTS),
    })
  })
  await page.route('**/chat/thread**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ agent_id: 'cli_agent', conversation_id: 'x', messages: [] }),
    })
  })
}

test('CLI chat shows one cascading picker with agent / model / effort pills', async ({
  page,
}) => {
  await stubApis(page)
  await page.goto('/chat?blueprint=cli_agent&mode=cli&cli=agy&model=gemini-3.8-flash-medium')
  const picker = page.getByTestId('navbar-routing-picker')
  await expect(picker).toHaveCount(1)
  await expect(page.getByRole('combobox', { name: 'CLI' })).toHaveCount(0)
  await expect(page.getByRole('combobox', { name: 'Model' })).toHaveCount(0)
  await expect(page.getByTestId('routing-pill-agent')).toHaveText(/agy/)
  await expect(page.getByTestId('routing-pill-model')).toHaveText(/gemini-3.8-flash/)
  await expect(page.getByTestId('routing-pill-effort')).toHaveText(/medium/)
  await expect(page.getByTestId('routing-face')).toHaveAttribute(
    'title',
    'agy / gemini-3.8-flash / medium',
  )
  await page.getByTestId('routing-pill-effort').click()
  await page.getByRole('menuitem', { name: 'high' }).click()
  await expect(page.getByTestId('routing-pill-effort')).toHaveText(/high/)
  await expect(page.getByTestId('routing-pill-agent')).toHaveAttribute('data-value', 'agy')
  await page.screenshot({
    path: `${artifactsDir()}/navbar-routing-picker-pills.png`,
  })
})

test('the routing flyout is not clipped by the chat header (#445)', async ({ page }) => {
  // .os-chat-header sets overflow: hidden for title truncation, and the flyout
  // used to be an absolutely-positioned child of it — so everything past the
  // first row was painted outside the clip and could not be clicked.
  await stubApis(page)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/chat?blueprint=cli_agent&mode=cli&cli=agy&model=gemini-3.8-flash-medium')

  await page.getByTestId('routing-pill-agent').click()
  const menu = page.getByTestId('routing-menu-agent')
  await expect(menu).toBeVisible()

  // Every row must be reachable, not just the first: the flyout's lower rows are
  // exactly what the header clip used to hide.
  const rows = menu.getByRole('menuitem')
  const rowsI = await rows.count()
  expect(rowsI, 'the menu has several rows').toBeGreaterThan(1)
  for (let i = 0; i < rowsI; i += 1) {
    const box = await rows.nth(i).boundingBox()
    expect(box, `row ${i} has a box`).not.toBeNull()
    const hit = await page.evaluate(
      ({ x, y }) => {
        const el = document.elementFromPoint(x, y)
        if (!el) return 'nothing'
        return el.closest('[data-testid="routing-flyout"]') ? 'flyout' : el.tagName.toLowerCase()
      },
      { x: box!.x + box!.width / 2, y: box!.y + box!.height / 2 },
    )
    expect(hit, `row ${i} is the element under its own centre`).toBe('flyout')
  }
  await page.screenshot({ path: `${artifactsDir()}/req445-routing-flyout-unclipped.png` })

  // And a lower agent row is clickable the way the operator clicks it. (The
  // menu's very last row is the Manage action, hit-tested in the loop above.)
  await menu.getByTestId('routing-option-agent-grok').click()
  await expect(page.getByTestId('routing-pill-agent')).toHaveAttribute('data-value', 'grok')

  // The header stopped clipping, so the title contract has to hold on its own:
  // the label clamps, and nothing escapes sideways.
  await page.setViewportSize({ width: 1024, height: 800 })
  await page.goto('/chat?blueprint=cli_agent_long&mode=cli&cli=agy&model=gemini-3.8-flash-medium')
  const title = page.locator('.os-navbar-identity-label')
  await expect(title).toBeVisible()
  const clamp = await title.evaluate((el) => ({
    scrollWidth: el.scrollWidth,
    clientWidth: el.clientWidth,
    whiteSpace: getComputedStyle(el).whiteSpace,
  }))
  expect(clamp.whiteSpace, 'title stays on one line').toBe('nowrap')
  expect(clamp.scrollWidth, 'title is clamped, not wrapped').toBeGreaterThan(clamp.clientWidth)
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  )
  expect(overflow, 'the page does not scroll sideways').toBeLessThanOrEqual(1)
})

test('RTL smoke: cascade still opens from the single picker', async ({ page }) => {
  await stubApis(page)
  await page.addInitScript(() => {
    document.documentElement.setAttribute('dir', 'rtl')
  })
  await page.goto('/chat?blueprint=cli_agent&mode=cli&cli=agy&model=gemini-3.8-flash-medium')
  await expect(page.getByTestId('navbar-routing-picker')).toBeVisible()
  await page.getByTestId('routing-pill-agent').click()
  await expect(page.getByTestId('routing-menu-agent')).toBeVisible()
  await page.getByTestId('routing-pill-model').click()
  await expect(page.getByTestId('routing-menu-model')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('routing-menu-model')).toHaveCount(0)
})

test('blueprint seats do not grow a You/Default routing picker', async ({ page }) => {
  await stubApis(page)
  await page.goto('/chat?blueprint=codey')
  await expect(page.getByRole('heading', { name: 'Codey' })).toBeVisible()
  await expect(page.getByTestId('navbar-routing-picker')).toHaveCount(0)
  await expect(page.getByTestId('api-select')).toHaveCount(0)
  await expect(page.getByTestId('api-model-select')).toHaveCount(0)
})
