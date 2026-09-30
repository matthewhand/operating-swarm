/**
 * REQ-13 — Chat Send path with MOCK inference (no live LLM).
 *
 * Run from webui/frontend:
 *   npm ci
 *   npx playwright install chromium
 *   npx playwright test e2e/chat-send.spec.ts
 *
 * Files:
 *   e2e/chat-send.spec.ts          (this file)
 *   e2e/helpers/mockInference.ts   (in-page WebSocket mock + /v1 stubs)
 */
import { test, expect } from '@playwright/test'
import {
  installMockInference,
  mockInferenceState,
  MOCK_FAST_REPLY,
  MOCK_SLOW_REPLY,
  SLOW_INFERENCE_DELAY_MS,
} from './helpers/mockInference'

/**
 * REQ-8 (PR 312) removes the standing Connected badge — healthy is silent,
 * errors toast. Ready = conversation log + enabled composer, not a status chip.
 * Do not reintroduce Connected here.
 */
async function awaitComposerReady(page: import('@playwright/test').Page) {
  const conversation = page.getByRole('log', { name: 'Conversation' })
  await expect(conversation).toBeVisible()
  const composer = page.getByRole('textbox', { name: 'Chat message' })
  await expect(composer).toBeEnabled()
  await expect(composer).toHaveAttribute('placeholder', /^Message /)
  return { conversation, composer }
}

async function sendChatMessage(page: import('@playwright/test').Page, text: string) {
  const { composer } = await awaitComposerReady(page)
  await composer.fill(text)
  // REQ-76: circular up-arrow Send appears once the field has text.
  await expect(page.getByRole('button', { name: /^Send$/i })).toBeEnabled()
  await composer.press('Enter')
}

test.describe('REQ-13 chat Send mock inference', () => {
  test('FAST mock: type, Send, assistant reply renders in well under 2s', async ({
    page,
  }) => {
    await installMockInference(page, { delayMs: 0, reply: MOCK_FAST_REPLY })
    await page.goto('/chat')

    const { conversation } = await awaitComposerReady(page)

    const prompt = 'Hello from the FAST mock'
    const started = Date.now()
    await sendChatMessage(page, prompt)

    await expect(conversation.getByText(prompt)).toBeVisible()
    await expect(conversation.getByText(MOCK_FAST_REPLY)).toBeVisible()
    const elapsedMs = Date.now() - started
    expect(
      elapsedMs,
      `FAST mock reply took ${elapsedMs}ms (aim <2000ms, hard cap 60s)`,
    ).toBeLessThan(2000)

    const state = await mockInferenceState(page)
    expect(state.delivered).toBe(1)
    expect(state.lastPrompt).toBe(prompt)

    // Send is not stuck after the reply: composer accepts a follow-up.
    await page.getByRole('textbox', { name: 'Chat message' }).fill('follow-up')
    await expect(page.getByRole('button', { name: /^Send$/i })).toBeEnabled()
    await expect(page.getByText(/timed?\s*out/i)).toHaveCount(0)
  })

  test('SLOW mock: assistant reply after >60s (fake clock) still renders', async ({
    page,
  }) => {
    expect(SLOW_INFERENCE_DELAY_MS).toBeGreaterThan(60_000)

    // Fake the clock so CI does not sleep 61s. The mock still schedules a
    // real >60s timer; we jump the page clock across it.
    await page.clock.install()
    await installMockInference(page, {
      delayMs: SLOW_INFERENCE_DELAY_MS,
      reply: MOCK_SLOW_REPLY,
    })
    await page.goto('/chat')

    const { conversation } = await awaitComposerReady(page)

    const prompt = 'Hello from the SLOW mock'
    await sendChatMessage(page, prompt)

    await expect(conversation.getByText(prompt)).toBeVisible()
    await expect(conversation.getByText(MOCK_SLOW_REPLY)).toHaveCount(0)

    const pending = await mockInferenceState(page)
    expect(pending.delayMs).toBe(SLOW_INFERENCE_DELAY_MS)
    expect(pending.delivered).toBe(0)

    // Still waiting at 59s — proves the mock is actually on the >60s path.
    await page.clock.fastForward(59_000)
    await expect(conversation.getByText(MOCK_SLOW_REPLY)).toHaveCount(0)
    expect((await mockInferenceState(page)).delivered).toBe(0)

    // Cross the 61s delay. Reply must appear; no false timeout / silent drop.
    await page.clock.fastForward(2_000)
    await expect(conversation.getByText(MOCK_SLOW_REPLY)).toBeVisible()
    expect((await mockInferenceState(page)).delivered).toBe(1)

    await expect(page.getByText(/timed?\s*out/i)).toHaveCount(0)
    await page.getByRole('textbox', { name: 'Chat message' }).fill('after-slow')
    await expect(page.getByRole('button', { name: /^Send$/i })).toBeEnabled()
  })
})
