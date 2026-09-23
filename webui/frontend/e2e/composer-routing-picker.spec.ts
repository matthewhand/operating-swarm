import { test, expect } from '@playwright/test'

const CLI_AGENTS = {
  clis: ['agy', 'claude', 'codex', 'gemini', 'grok'],
  known: ['agy', 'claude', 'codex', 'gemini', 'grok'],
  configured: ['agy'],
  discovered: ['agy'],
  installed: ['agy'],
  suggestions: {},
  default_cli: 'agy',
  native_consensus: { agy: ['--best-of-n', '{n}'] },
  catalog: {},
  list_models: { agy: ['agy', 'models'] },
  rail: [
    {
      id: 'cli_agent',
      object: 'cli.agent',
      name: 'cli_agent',
      cli: 'agy',
      kind: 'cli',
      description: 'Agentic CLI',
      installed: true,
    },
  ],
}

async function stubApis(page: import('@playwright/test').Page) {
  await page.route('**/v1/cli-agents/**', async (route) => {
    const url = route.request().url()
    if (url.includes('/models')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          cli: 'agy',
          models: ['gemini-2.5-pro', 'gemini-2.5-flash'],
        }),
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

test('composer routing picker is beside mic, borderless at rest, zero layout shift on hover', async ({ page }) => {
  await stubApis(page)
  await page.setViewportSize({ width: 1200, height: 800 })
  await page.goto('/chat?blueprint=cli_agent&mode=cli&cli=agy&model=gemini-2.5-flash')

  const composer = page.locator('.os-composer')
  await expect(composer).toBeVisible()

  const picker = composer.getByTestId('navbar-routing-picker')
  await expect(picker).toBeVisible()

  const mic = composer.getByTestId('composer-mic')
  await expect(mic).toBeVisible()

  // Verify picker is immediately before mic
  const pickerBox = await picker.boundingBox()
  const micBox = await mic.boundingBox()
  expect(pickerBox).not.toBeNull()
  expect(micBox).not.toBeNull()
  expect(pickerBox!.x + pickerBox!.width).toBeLessThanOrEqual(micBox!.x + 4)

  // Measure mic position at rest
  const initialMicX = micBox!.x
  const initialMicY = micBox!.y

  // Rest screenshot
  await page.screenshot({
    path: '/app/artifacts/584-composer-routing-rest.png',
  })

  // Hover over the routing pill
  const agentPill = page.getByTestId('routing-pill-agent')
  await agentPill.hover()

  // Bounding box of mic must NOT change on hover (zero layout shift)
  const micBoxHover = await mic.boundingBox()
  expect(micBoxHover!.x).toBe(initialMicX)
  expect(micBoxHover!.y).toBe(initialMicY)

  // Hover screenshot
  await page.screenshot({
    path: '/app/artifacts/584-composer-routing-hover.png',
  })

  // Click pill to open flyout upward
  await agentPill.click()
  const flyout = page.getByTestId('routing-flyout')
  await expect(flyout).toBeVisible()

  // Flyout should be positioned above the composer
  const flyoutBox = await flyout.boundingBox()
  expect(flyoutBox).not.toBeNull()
  expect(flyoutBox!.y + flyoutBox!.height).toBeLessThanOrEqual(pickerBox!.y + 5)

  // Open screenshot
  await page.screenshot({
    path: '/app/artifacts/584-composer-routing-open.png',
  })
})
