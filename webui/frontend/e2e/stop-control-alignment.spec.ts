/**
 * D1 — the per-agent Stop control aligns to the message content axis for the
 * active bubble theme (not flush to the transcript row's far left).
 *
 * Before: every theme rendered the stop slot at the row's left edge
 * (`mt-1 flex justify-start`), so on speech it sat under the beside-bubble
 * avatar and on IRC to the left of the name gutter — disconnected from the
 * message input's text axis. Now the slot carries a per-theme axis contract
 * and an offset that lands it on the bubble/content column.
 *
 * jsdom cannot measure layout; this pins the rendered geometry.
 */
import { test, expect, type Page } from '@playwright/test'

const BLUEPRINTS = {
  object: 'list',
  data: [{ id: 'support', object: 'blueprint', name: 'Support', description: 'Helper', installed: true, compiled: true, rail: true }],
}

async function stubApis(page: Page) {
  await page.route('**/v1/blueprints**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(BLUEPRINTS) }),
  )
  for (const pattern of ['**/v1/models**', '**/v1/teams**']) {
    await page.route(pattern, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ object: 'list', data: [] }) }),
    )
  }
  await page.route('**/v1/remotes**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ object: 'list', kinds: [], configured: [], data: [] }) }),
  )
  await page.route('**/health**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) }),
  )
  await page.route('**/chat/thread**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ agent_id: 'support', conversation_id: 'stop-align-e2e', messages: [], summaries: [] }),
    }),
  )
}

async function installStreamingMock(page: Page) {
  await page.addInitScript(() => {
    class MockWs {
      static CONNECTING = 0; static OPEN = 1; static CLOSING = 2; static CLOSED = 3
      url = ''; readyState = 0
      onopen: ((e: Event) => void) | null = null
      onmessage: ((e: MessageEvent) => void) | null = null
      onclose: ((e: CloseEvent) => void) | null = null
      onerror: ((e: Event) => void) | null = null
      constructor(url: string) { this.url = url; queueMicrotask(() => { this.readyState = 1; this.onopen?.(new Event('open')) }) }
      send(data: string) {
        let message = ''
        try { message = (JSON.parse(data).message as string) ?? '' } catch { return }
        if (!message.trim()) return
        const id = 'message-response-stopalign'
        this.emit(`<div id="message-list" hx-swap-oob="beforeend"><div class="user-message">${message}</div></div>`)
        this.emit(`<div id="message-list" hx-swap-oob="beforeend"><div id="${id}" class="assistant-message"></div></div>`)
        // Start frame + a chunk, then stay streaming so the stop renders.
        this.emit(`<div hx-swap-oob="beforeend:#${id}">Streaming partial answer in flight. </div>`)
      }
      close(code = 1000) { this.readyState = 3; this.onclose?.(new CloseEvent('close', { code })) }
      private emit(text: string) { this.onmessage?.(new MessageEvent('message', { data: text })) }
    }
    ;(window as any).WebSocket = MockWs
  })
}

function metrics(page: Page) {
  return page.evaluate(() => {
    const stop = document.querySelector('[data-testid="agent-row-stop"]') as HTMLElement
    const slot = document.querySelector('[data-testid="agent-row-stop-slot"]') as HTMLElement
    const row = stop.closest('.os-chat-row') as HTMLElement
    const bubble = row.querySelector('.chat-bubble') as HTMLElement
    const input = document.querySelector('.os-composer__input, textarea[aria-label="Chat message"]') as HTMLElement
    return {
      stopLeft: +stop.getBoundingClientRect().left.toFixed(1),
      rowLeft: +row.getBoundingClientRect().left.toFixed(1),
      bubbleLeft: +bubble.getBoundingClientRect().left.toFixed(1),
      inputLeft: +input.getBoundingClientRect().left.toFixed(1),
      axis: slot.getAttribute('data-stop-axis'),
    }
  })
}

const EXPECTED_AXIS: Record<string, string> = { speech: 'bubble', simple: 'bubble', irc: 'line' }

for (const theme of ['speech', 'simple', 'irc']) {
  test(`stop aligns to the message content axis — ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await page.addInitScript((t) => localStorage.setItem('os.bubbleTheme', t), theme)
    await stubApis(page)
    await installStreamingMock(page)
    await page.goto('/chat')
    const composer = page.getByRole('textbox', { name: 'Chat message' })
    await expect(composer).toBeEnabled()
    await composer.fill('Stream please')
    await composer.press('Enter')
    await expect(page.getByTestId('running-status-badge')).toBeVisible()
    await page.getByTestId('running-status-badge').hover()
    await expect(page.getByTestId('agent-row-stop')).toBeVisible()
    await page.waitForTimeout(200)

    const m = await metrics(page)
    expect(m.axis, `${theme} axis`).toBe(EXPECTED_AXIS[theme])

    if (theme === 'speech') {
      // Speech keeps the beside-bubble avatar: the stop indents to the bubble
      // column (>= 2rem past the row), not flush left.
      expect(m.stopLeft, 'speech stop clears the avatar column').toBeGreaterThan(m.rowLeft + 24)
      expect(Math.abs(m.stopLeft - m.bubbleLeft), 'speech stop sits on the bubble axis').toBeLessThanOrEqual(1)
    } else if (theme === 'simple') {
      // No beside-bubble avatar: the bubble is flush with the row, and so is
      // the stop.
      expect(Math.abs(m.stopLeft - m.bubbleLeft), 'simple stop sits on the bubble axis').toBeLessThanOrEqual(1)
    } else {
      // IRC line layout: the stop clears the row's far left and lands on the
      // gutter/content column rather than under the transcript edge.
      expect(m.stopLeft, 'irc stop clears the row edge').toBeGreaterThan(m.rowLeft + 24)
    }
  })
}
