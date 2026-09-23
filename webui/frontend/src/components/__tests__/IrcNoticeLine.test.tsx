/**
 * #782 — IrcNoticeLine: the gutter-line renderer for not-message rows
 * (status notices, session messages, rate-limit lines) under the IRC theme.
 *
 * Contract: identical chrome to a real IRC message row — right-aligned
 * `<speaker>` gutter, one straight vertical divider, inline time cell
 * (`--:--` when the timestamp is unknown, per #774) — so the transcript
 * speaks one visual language and the column never breaks.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { IrcNoticeLine } from '../IrcNoticeLine'

describe('IrcNoticeLine (#782)', () => {
  it('renders the speaker gutter, divider and inline time', () => {
    render(
      <IrcNoticeLine
        speaker="System"
        text="Started a new omp session"
        ts="2026-09-20T10:30:00Z"
        rowKey="notice-1"
      />,
    )
    const row = screen.getByTestId('irc-notice-line')
    expect(row.dataset.speaker).toBe('System')
    expect(row.dataset.ts).toBeTruthy()
    expect(screen.getByTestId('irc-gutter-divider')).toBeTruthy()
    expect(screen.getByTestId('bubble-time').textContent).not.toBe('--:--')
    expect(screen.getByTestId('irc-notice-text').textContent).toBe('Started a new omp session')
  })

  it('shows the honest --:-- cell when ts is unknown (#774)', () => {
    render(<IrcNoticeLine speaker="System" text="Queued item promoted." rowKey="notice-2" />)
    expect(screen.getByTestId('bubble-time').textContent).toBe('--:--')
    expect(screen.getByTestId('irc-notice-line').dataset.ts).toBeUndefined()
  })

  it('exposes an optional click action (rate-limit lines open settings)', () => {
    let clicked = 0
    render(
      <IrcNoticeLine
        speaker="System"
        text="Rate limited by provider"
        rowKey="notice-3"
        onClick={() => {
          clicked += 1
        }}
      />,
    )
    const row = screen.getByTestId('irc-notice-line')
    expect(row.getAttribute('role')).toBe('button')
    row.click()
    expect(clicked).toBe(1)
  })

  it('stays a plain line without onClick', () => {
    render(<IrcNoticeLine speaker="System" text="plain" rowKey="notice-4" />)
    expect(screen.getByTestId('irc-notice-line').getAttribute('role')).toBeNull()
  })
})
