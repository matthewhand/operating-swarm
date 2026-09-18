/**
 * #595 — while a turn is in flight, the composer's Stop button takes the
 * microphone's place instead of becoming a fifth icon in the trailing row.
 *
 * The row changing width mid-conversation (an extra control appended beside
 * the mic) moves everything underneath the pointer while the user types.
 * Swapping keeps the row's control count constant:
 *   idle  → [mic] …
 *   busy  → [stop] …   (mic hidden, not gone — it returns when idle)
 *
 * Existing ChatPage.queued tests already pin the lifecycle (absent when idle,
 * present while in flight, gone after stop), so this file pins the swap
 * invariants in the source: one `composerBusy` signal, mic and stop mutually
 * exclusive through it.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const src = readFileSync(join(process.cwd(), 'src/pages/ChatPage.tsx'), 'utf8')

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

/** The JSX expression text immediately wrapping an element (up to 200 chars). */
function wrapperCondition(testid: string): string {
  const anchor = src.indexOf(`data-testid="${testid}"`)
  const elemStart = src.lastIndexOf('<button', anchor)
  const before = src.slice(0, elemStart)
  const brace = before.lastIndexOf('{')
  return before.slice(brace, brace + 220)
}

describe('#595: Stop swaps into the microphone slot', () => {
  it('one composerBusy signal derives both controls', () => {
    expect(src).toContain(
      'const composerBusy = status === \'open\' && generationIsInFlight(messages, awaitingAssistant)',
    )
  })

  it('the mic renders only while the composer is NOT busy', () => {
    expect(wrapperCondition('composer-mic')).toMatch(/!\s*composerBusy/)
  })

  it('the stop button renders only while the composer IS busy', () => {
    // The stop button is the ELSE branch of the same conditional the mic
    // occupies — its wrapper is the ternary delimiter, not a negation.
    const anchor = src.indexOf('data-testid="composer-stop"')
    const elemStart = src.lastIndexOf('<button', anchor)
    const before = src.slice(0, elemStart)
    expect(before.slice(-30)).toMatch(/\) : \(\s*$/)
    const cond = wrapperCondition('composer-mic')
    expect(cond).toMatch(/!\s*composerBusy/)
  })

  it('the stop button no longer duplicates the old inline in-flight condition', () => {
    // The old markup re-stated the full condition inline, appended after an
    // unconditional mic; both must be gone in favour of the swap.
    const stop = elementFor('composer-stop')
    expect(stop).not.toContain('generationIsInFlight')
  })
})
