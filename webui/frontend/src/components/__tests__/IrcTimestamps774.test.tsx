/**
 * #774 — IRC theme: time on every line, divider never misaligned.
 *
 * Two defects pinned here:
 *   1. Rows whose `ts` is unknown (fresh WS rows, restored CLI transcripts)
 *      rendered NO timestamp in the IRC gutter — intermittent gaps.
 *   2. System-preload rows early-returned before the gutter divider, so the
 *      vertical divider line visibly broke at those rows.
 *
 * Contract: IRC renders a timestamp cell on EVERY row — the real time when
 * known, an honest `--:--` when not — and every row carries the divider.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ChatMessageBubble } from '../ChatMessageBubble'

function renderRow(overrides: Partial<Parameters<typeof ChatMessageBubble>[0]> = {}) {
  const props: Parameters<typeof ChatMessageBubble>[0] = {
    role: 'assistant',
    agentName: 'Support',
    text: 'hello',
    streaming: false,
    editing: false,
    onCancelEdit: () => {},
    onSaveEdit: () => {},
    theme: 'irc',
    ...overrides,
  }
  return render(<ChatMessageBubble {...props} />)
}

describe('#774 IRC — timestamp on every line', () => {
  it('renders --:-- when ts is unknown (assistant row)', () => {
    renderRow({ ts: undefined })
    const time = screen.getByTestId('bubble-time')
    expect(time.textContent).toBe('--:--')
  })

  it('renders --:-- when ts is invalid', () => {
    renderRow({ ts: 'not-a-date' })
    expect(screen.getByTestId('bubble-time').textContent).toBe('--:--')
  })

  it('renders the real time when ts is known', () => {
    renderRow({ ts: new Date('2026-09-20T10:30:00Z').toISOString() })
    const time = screen.getByTestId('bubble-time')
    expect(time.textContent).not.toBe('')
    expect(time.textContent).not.toBe('--:--')
  })

  it('status rows show a timestamp too', () => {
    renderRow({ role: 'status', ts: undefined })
    expect(screen.getByTestId('bubble-time').textContent).toBe('--:--')
  })

  it('non-IRC themes do not gain the placeholder', () => {
    renderRow({ theme: 'speech', ts: undefined })
    expect(screen.queryByTestId('bubble-time')).toBeNull()
  })
})

describe('#774 IRC — divider on every row', () => {
  it('system-preload rows still render the gutter divider', () => {
    renderRow({ role: 'system', isSystemPreload: true })
    expect(screen.getByTestId('irc-gutter-divider')).toBeTruthy()
  })

  it('regular rows render the gutter divider', () => {
    renderRow()
    expect(screen.getByTestId('irc-gutter-divider')).toBeTruthy()
  })
})
