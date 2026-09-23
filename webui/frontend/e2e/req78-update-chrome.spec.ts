import { test, expect } from '@playwright/test'
import path from 'node:path'
import { artifactsDir } from './helpers/artifacts'

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

async function stubApis(page: import('@playwright/test').Page, githubTag: string | null) {
  await page.route('**/api.github.com/**', async (route) => {
    if (githubTag) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          tag_name: githubTag,
          html_url: `https://github.com/matthewhand/open-swarm/releases/tag/${githubTag}`,
        }),
      })
      return
    }
    await route.fulfill({ status: 503, contentType: 'application/json', body: '{}' })
  })
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
}

function shot(name: string): string {
  return path.join(artifactsDir(), name)
}

test('REQ-78 XOR chrome sits right of the system name', async ({ page }) => {
  await stubApis(page, null)
  await page.goto('/chat')

  const hostname = page.getByLabel('Hostname')
  const chrome = page.getByTestId('rail-update-chrome')
  const server = page.getByTestId('rail-server-icon')
  await expect(hostname).toBeVisible()
  await expect(chrome).toBeVisible()
  await expect(server).toBeVisible()
  await expect(chrome).toHaveAttribute('data-kind', 'idle')
  await expect(chrome).toHaveAttribute('aria-label', 'Operating Swarm issues')

  const order = await page.evaluate(() => {
    const row = document.querySelector('.os-rail-hostname-row')
    const ids = [row?.querySelector('[data-testid="rail-server-icon"]') ? 'server' : '', 'hostname']
    if (row?.querySelector('[data-testid="rail-update-chrome"]')) ids.push('chrome')
    return ids.filter(Boolean)
  })
  expect(order).toEqual(['server', 'hostname', 'chrome'])

  await page.locator('.os-rail-hostname-row').screenshot({
    path: shot('req78-idle-info.png'),
  })
  await page.locator('[data-testid="os-agent-rail"]').screenshot({
    path: shot('req78-rail-idle.png'),
  })

  await page.evaluate(() => {
    window.dispatchEvent(new CustomEvent('swarm:spa-hello', { detail: '9.9.9' }))
  })
  await expect(chrome).toHaveAttribute('data-kind', 'local')
  await expect(chrome).toHaveAttribute('aria-label', 'Reload to update this tab')
  await page.locator('.os-rail-hostname-row').screenshot({
    path: shot('req78-local-amber.png'),
  })
})

test('REQ-78 GitHub newer only paints the sky cloud', async ({ page }) => {
  await stubApis(page, 'v99.0.0')
  await page.goto('/chat')
  const chrome = page.getByTestId('rail-update-chrome')
  await expect(chrome).toHaveAttribute('data-kind', 'upstream')
  await expect(chrome).toHaveAttribute('aria-label', 'Newer Operating Swarm release available')
  await page.locator('.os-rail-hostname-row').screenshot({
    path: shot('req78-upstream-sky.png'),
  })
})
