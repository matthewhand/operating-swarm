import { describe, expect, it } from 'vitest'
import {
  insertCliSessionNotice,
  isCliSessionNoticeText,
  isNewCliSessionNoticeText,
  transcriptAlreadyHasNotice,
} from '../chatTranscript'

describe('CLI session notice transcript order (REQ-92)', () => {
  it('recognises new-session and resume copy only', () => {
    expect(isNewCliSessionNoticeText('Started a new grok session.')).toBe(true)
    expect(isCliSessionNoticeText('Resumed opencode session.')).toBe(true)
    expect(isNewCliSessionNoticeText('Resumed grok session.')).toBe(false)
    expect(isCliSessionNoticeText('CLI: antigravity → grok')).toBe(false)
  })

  it('inserts a new-session line immediately before this turn assistant', () => {
    const next = insertCliSessionNotice(
      [
        { role: 'user', text: 'hello' },
        { role: 'assistant', text: 'hi' },
      ],
      { role: 'status', text: 'Started a new grok session.' },
    )
    expect(next.map((row) => row.role)).toEqual(['user', 'status', 'assistant'])
    expect(next[1]?.text).toBe('Started a new grok session.')
  })

  it('does not invent a second new-session line on resume / same turn', () => {
    const current = [
      { role: 'user', text: 'hello' },
      { role: 'status', text: 'Started a new grok session.' },
      { role: 'assistant', text: 'hi' },
      { role: 'user', text: 'again' },
      { role: 'assistant', text: '' },
    ]
    expect(transcriptAlreadyHasNotice(current, 'Started a new grok session.')).toBe(false)
    const resumed = insertCliSessionNotice(current, {
      role: 'status',
      text: 'Resumed grok session.',
    })
    expect(resumed.map((row) => `${row.role}:${row.text}`)).toEqual([
      'user:hello',
      'status:Started a new grok session.',
      'assistant:hi',
      'user:again',
      'status:Resumed grok session.',
      'assistant:',
    ])
    const dup = insertCliSessionNotice(resumed, {
      role: 'status',
      text: 'Resumed grok session.',
    })
    expect(dup).toEqual(resumed)
    expect(resumed.some((row) => row.text === 'Started a new grok session.')).toBe(true)
    expect(resumed.filter((row) => row.text?.startsWith('Started a new')).length).toBe(1)
  })

  it('treats a hop notice as covering the short new-session line (REQ-866)', () => {
    const hop =
      'Started a new grok session (antigravity → grok). No prior context to carry from antigravity.'
    const afterSend = [
      { role: 'user', text: 'hello' },
      { role: 'assistant', text: 'hi' },
      { role: 'status', text: hop },
      { role: 'user', text: 'next' },
    ]
    expect(transcriptAlreadyHasNotice(afterSend, 'Started a new grok session.')).toBe(true)
    expect(transcriptAlreadyHasNotice(afterSend, 'Started a new omp session.')).toBe(false)
  })

  it('appends dropdown status after the assistant (REQ-46)', () => {
    const next = insertCliSessionNotice(
      [
        { role: 'user', text: 'hello' },
        { role: 'assistant', text: 'hi' },
      ],
      { role: 'status', text: 'CLI: antigravity → grok' },
    )
    expect(next.map((row) => row.role)).toEqual(['user', 'assistant', 'status'])
  })
})
