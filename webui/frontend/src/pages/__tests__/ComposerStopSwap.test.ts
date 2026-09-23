/**
 * #632 (supersedes the #595 swap) — the composer's primary action lives
 * OUTSIDE the input box, to its right:
 *
 *   idle, no draft      → [ .os-composer pill ] (no outer button)
 *   idle, draft         → [ pill ][ ↑ send ]
 *   busy                → [ pill ][ □ stop ]   (mic stays INSIDE the pill)
 *
 * The outer slot keeps one primary action at all times; the mic no longer
 * disappears mid-conversation. Existing ChatPage.queued tests pin the
 * lifecycle (absent when idle, present while in flight, gone after settle);
 * this file pins the structural invariants in the source.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

// #856 slice H: the composer markup moved verbatim into ChatBottomDock.tsx;
// #856 slice 18: the composerBusy derivation moved verbatim into
// useTranscriptLayout.tsx. Union read keeps all three pins.
const src =
  readFileSync(join(process.cwd(), 'src/pages/ChatPage.tsx'), 'utf8') +
  readFileSync(join(process.cwd(), 'src/features/chat/ChatBottomDock.tsx'), 'utf8') +
  readFileSync(join(process.cwd(), 'src/features/chat/useTranscriptLayout.tsx'), 'utf8')

/** The JSX element carrying the given composer testid. */
function elementFor(testid: string): string {
  const anchor = src.indexOf(`data-testid="${testid}"`)
  expect(anchor, `${testid} exists`).toBeGreaterThan(0)
  const start = src.lastIndexOf('<button', anchor)
  const end = src.indexOf('</button>', anchor)
  expect(start).toBeGreaterThan(0)
  expect(end).toBeGreaterThan(anchor)
  return src.slice(start, end + '</button>'.length)
}

describe('#632: outer send/stop slot', () => {
  it('one composerBusy signal derives the morph', () => {
    expect(src).toContain(
      "const composerBusy = status === 'open' && generationIsInFlight(messages, awaitingAssistant)",
    )
  })

  it('the mic is unconditional — it never disappears while busy', () => {
    const anchor = src.indexOf('data-testid="composer-mic"')
    const elemStart = src.lastIndexOf('<button', anchor)
    const before = src.slice(0, elemStart)
    // The mic must not sit behind a `!composerBusy` ternary anymore.
    expect(before.slice(-120)).not.toMatch(/!\s*composerBusy\s*\?/)
    expect(src).toContain('data-testid="composer-mic"')
  })

  it('the stop button renders while busy, carrying the morph class', () => {
    const stop = elementFor('composer-stop')
    expect(stop).toContain('os-composer__send--stop')
    expect(stop).toContain('interruptRunningTurn')
  })

  it('the outer slot carries send and stop — no inline in-flight condition re-stated', () => {
    const stop = elementFor('composer-stop')
    expect(stop).not.toContain('generationIsInFlight')
    expect(src).toContain("className=\"os-composer__send\"")
  })

  it('send and stop share one outer slot beside the pill (CSS contract)', () => {
    const css = readFileSync(join(process.cwd(), 'src/index.css'), 'utf8')
    expect(css).toContain('.os-composer-row {')
    expect(css).toContain('.os-composer__send--stop {')
  })
})
