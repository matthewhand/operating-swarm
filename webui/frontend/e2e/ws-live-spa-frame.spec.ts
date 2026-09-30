/**
 * ADR-017 PR-3 (#1118) — live render over the whole-SPA multiplex socket.
 *
 * spa_multiplex.py tags every headless consumer reply as
 *   {kind:'spa.frame', conversationId, data:<inner>}
 * where a non-JSON (HTMx) payload arrives as `data.text`. spaSocket.ts must
 * unwrap that envelope and parse the HTML inside `data.text`, or an assistant
 * reply simply never lands in the transcript.
 *
 * The mock WebSocket (helpers/mockInference.ts, `envelope:'spa'`) is replaced
 * in-page, so this is deterministic and needs no live LLM.
 */
import { test, expect } from '@playwright/test'
import {
  installMockInference,
  mockInferenceState,
} from './helpers/mockInference'

const LIVE_REPLY = 'SPA_FRAME_LIVE_REPLY'

test.describe('live WS render through the SPA multiplex envelope', () => {
  test('assistant reply renders live from a spa.frame without a reload (#1118)', async ({
    page,
  }) => {
    const jsErrors: string[] = []
    page.on('pageerror', (e) => jsErrors.push(e.message))

    await page.route('**/chat/thread**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          agent_id: 'support',
          conversation_id: 'spa-live-e2e',
          messages: [],
          summaries: [],
        }),
      })
    })
    await installMockInference(page, { envelope: 'spa', reply: LIVE_REPLY })
    await page.goto('/chat')

    const composer = page.getByRole('textbox', { name: 'Chat message' })
    await expect(composer).toBeEnabled()

    // A reload would replace the document and drop this marker — proving the
    // reply was applied to the live DOM, not a full-page refresh.
    await page.evaluate(() => {
      ;(window as unknown as { __SPA_LIVE_MARKER__?: string }).__SPA_LIVE_MARKER__ = 'kept'
    })

    await composer.fill('hello over the mux')
    await composer.press('Enter')

    const conversation = page.getByRole('log', { name: 'Conversation' })
    await expect(conversation.getByText('hello over the mux')).toBeVisible()
    await expect(conversation.getByText(LIVE_REPLY)).toBeVisible()

    expect(
      await page.evaluate(
        () => (window as unknown as { __SPA_LIVE_MARKER__?: string }).__SPA_LIVE_MARKER__,
      ),
      'the reply must render without a manual reload',
    ).toBe('kept')

    const state = await mockInferenceState(page)
    expect(state.delivered).toBe(1)
    // The frame only round-trips if the mux envelope carried the conversation.
    expect(state.lastConversationId, 'spa.frame envelope was exercised').toBeTruthy()
    expect(jsErrors, `uncaught JS errors: ${jsErrors.join(' | ')}`).toHaveLength(0)
  })
})
