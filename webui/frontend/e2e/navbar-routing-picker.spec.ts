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
