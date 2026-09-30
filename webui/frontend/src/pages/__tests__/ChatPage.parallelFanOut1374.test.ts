/**
 * #1374 — the transcript stack is fed by fan-out leg frames, and stop
 * sends a cancel for that leg id. Kind strings do not mint the cards.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const srcOf = (rel: string) => readFileSync(join(process.cwd(), rel), 'utf8')

describe('#1374 ChatPage wires real fan-out legs', () => {
  it('sends a per-leg cancel and passes the live stack', () => {
    const src = srcOf('src/pages/ChatPage.tsx')
    expect(src).toContain('buildCancelFanOutLegFrame')
    expect(src).toContain('stopFanOutLeg')
    expect(src).toContain('fanOutLegs')
    expect(src).toContain('setFanOutLegs')
  })

  it('the transcript renders one card per fan-out leg', () => {
    const src = srcOf('src/features/chat/ChatMessageList.tsx')
    expect(src).toContain('cardsForFanOutLegs')
    expect(src).toContain('data-testid="running-card-stack"')
    expect(src).not.toContain('runningCardsForDisplay')
    expect(src).not.toMatch(/kind\s*===\s*['"]api['"]/)
  })

  it('the dispatcher folds fan_out_leg frames into the stack', () => {
    const src = srcOf('src/features/chat/useChatWsDispatcher.ts')
    expect(src).toContain("event.kind === 'fan_out_leg'")
    expect(src).toContain('applyFanOutLeg')
  })
})
