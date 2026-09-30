/**
 * #1202 follow-up — top navbar mobile fit + agent picker semantics.
 *
 * Visual proof at the two reference viewports plus DOM contracts:
 *  - mobile (390x844): the rail toggle is dropped, the role badge sits under
 *    the name as a slim pill, and the page does not overflow horizontally;
 *  - desktop (1440x900): the full navbar still renders;
 *  - the Agent control opens a menu of the *available agents* (not config).
 *
 * Screenshots land in /tmp/navbar-sweep as requested.
 */
import { mkdirSync } from 'node:fs'
import { test, expect } from '@playwright/test'

const SWEEP_DIR = '/tmp/navbar-sweep'

const BLUEPRINTS = {
  object: 'list',
  data: [
    {
      id: 'support',
      object: 'blueprint',
      name: 'Support',
      description: 'Socratic helper',
      role: 'support',
      tags: [],
      installed: true,
      compiled: true,
      rail: true,
    },
    {
      id: 'codey',
      object: 'blueprint',
      name: 'Codey',
      description: 'Code assistant',
      role: 'engineer',
      tags: [],
      installed: true,
      compiled: true,
      rail: true,
    },
  ],
}

const EMPTY = { object: 'list', data: [] }

async function stubApis(page: import('@playwright/test').Page) {
  await page.route('**/v1/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(EMPTY),
    }),
  )
  await page.route('**/v1/blueprints**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(BLUEPRINTS),
    }),
  )
  await page.route('**/v1/teams**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(EMPTY),
    }),
  )
  await page.route('**/v1/models**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(EMPTY),
    }),
  )
  await page.route('**/chat/thread**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ agent_id: 'support', conversation_id: 'x', messages: [] }),
    }),
  )
  await page.route('**/health**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok' }),
    }),
  )
}

test.beforeAll(() => {
  mkdirSync(SWEEP_DIR, { recursive: true })
})

test('mobile 390x844 fits without overflow, drops the rail toggle, badge under name', async ({
  page,
}) => {
  await stubApis(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/chat?blueprint=support')
  await expect(page.getByTestId('selected-agent-header')).toBeVisible()

  // DOM contract: no rail toggle on the mobile tier.
  await expect(page.getByRole('button', { name: 'Open agent list' })).toHaveCount(0)

  // Role badge is a slim pill inside the stacked identity text column.
  const badge = page.getByTestId('os-header-role-badge')
  await expect(badge).toBeVisible()
  await expect(badge).toHaveClass(/os-agent-role-badge--slim/)
  await expect(badge.locator('xpath=..')).toHaveClass(/os-navbar-identity-text/)

  const overflow = await page.evaluate(() => {
    const doc = document.documentElement
    const header = document.querySelector('header.os-chat-header') as HTMLElement | null
    const controls = document.querySelector('.os-chat-header__controls') as HTMLElement | null
    return {
      docOverflow: doc.scrollWidth - doc.clientWidth,
      headerOverflow: header ? header.scrollWidth - header.clientWidth : -1,
      controlsRight: controls ? Math.round(controls.getBoundingClientRect().right) : -1,
      docScrollWidth: doc.scrollWidth,
      docClientWidth: doc.clientWidth,
    }
  })
  console.log(`[navbar-mobile] ${JSON.stringify(overflow)}`)
  // The user-facing contract: the page never scrolls sideways.
  expect(overflow.docOverflow, 'document does not scroll sideways').toBeLessThanOrEqual(0)
  // The controls cluster stays inside the header box (1px is a pre-existing
  // hidden-modal sub-pixel artifact, not visible overflow).
  expect(overflow.headerOverflow, 'header does not visibly overflow').toBeLessThanOrEqual(1)
  expect(overflow.controlsRight).toBeLessThanOrEqual(overflow.docClientWidth)

  await page.screenshot({ path: `${SWEEP_DIR}/navbar-mobile.png` })
})

test('desktop 1440x900 renders the full navbar', async ({ page }) => {
  await stubApis(page)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/chat?blueprint=support')
  await expect(page.getByTestId('selected-agent-header')).toBeVisible()

  const overflow = await page.evaluate(() => {
    const doc = document.documentElement
    return { docOverflow: doc.scrollWidth - doc.clientWidth }
  })
  console.log(`[navbar-desktop] ${JSON.stringify(overflow)}`)
  expect(overflow.docOverflow).toBeLessThanOrEqual(0)

  await page.screenshot({ path: `${SWEEP_DIR}/navbar-desktop.png` })
})

test('agent picker lists available agents (not the current agent config)', async ({ page }) => {
  await stubApis(page)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/chat?blueprint=support')
  await expect(page.getByTestId('selected-agent-header')).toBeVisible()

  await page.getByTestId('os-navbar-agent-picker').click()
  const menu = page.getByTestId('os-navbar-agent-picker-menu')
  await expect(menu).toBeVisible()

  // The selectable agents are listed, and the current one is marked.
  expect(await menu.getByRole('menuitem').count()).toBeGreaterThanOrEqual(2)
  await expect(page.getByTestId('os-navbar-agent-option-codey')).toBeVisible()
  await expect(page.getByTestId('os-navbar-agent-option-support')).toHaveAttribute(
    'aria-current',
    'true',
  )

  await page.screenshot({ path: `${SWEEP_DIR}/agent-picker-open.png` })
})
