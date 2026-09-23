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
import fs from 'node:fs'
import path from 'node:path'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ChatMessageBubble } from '../ChatMessageBubble'
import { IrcNoticeLine } from '../IrcNoticeLine'

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
  it('system-preload rows are covered by the transcript gutter rail', () => {
    // #721 superseded the per-row divider: the transcript-level rail
    // (`.os-irc-gutter-rail`) spans every row including system preloads.
    const css = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf-8')
    expect(css).toMatch(/\.os-chat-transcript\[data-bubble-theme=['"]irc['"]\] \.os-irc-gutter-rail/)
  })

  it('notice rows render their own gutter divider span', () => {
    render(
      <IrcNoticeLine speaker="system" text="notice" rowKey="n1" />,
    )
    expect(screen.getByTestId('irc-gutter-divider')).toBeTruthy()
  })
})
