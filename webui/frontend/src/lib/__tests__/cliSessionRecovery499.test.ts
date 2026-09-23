/**
 * #499 — the recovery banner's primary action must reach the configuration
 * the message just named, not only reshuffle the session.
 */
import { describe, it, expect } from 'vitest'
import {
  configTargetFromText,
  isFatalConfigErrorMessage,
  lastRecoveryTarget,
} from '../cliSessionRecovery'

describe('#499 configTargetFromText', () => {
  it('maps unconfigured-CLI copy to the cli-agents section', () => {
    expect(configTargetFromText('No CLI agents are configured.')).toEqual({
      section: 'cli-agents',
    })
    expect(configTargetFromText('no cli backend is configured')).toEqual({
      section: 'cli-agents',
    })
  })

  it('maps harness/endpoint copy to remotes', () => {
    expect(configTargetFromText('Remote harness endpoint not configured yet')).toEqual({
      section: 'remotes',
    })
    expect(configTargetFromText('unconfigured harness')).toEqual({
      section: 'remotes',
    })
  })

  it('returns undefined for resume failures and unknown copy', () => {
    expect(configTargetFromText('[grok] failed: session not found')).toBeUndefined()
    expect(configTargetFromText('anything else')).toBeUndefined()
  })
})

describe('#499 lastRecoveryTarget', () => {
  it('prefers the server-stamped target on the last assistant turn', () => {
    expect(
      lastRecoveryTarget([
        { role: 'user', text: 'hi' },
        { role: 'assistant', text: 'unconfigured harness', configTarget: { section: 'remotes' } },
      ]),
    ).toEqual({ section: 'remotes' })
  })

  it('derives the target from text for legacy rows without a stamp', () => {
    expect(
      lastRecoveryTarget([
        { role: 'user', text: 'hi' },
        { role: 'assistant', text: 'No CLI agents are configured.' },
      ]),
    ).toEqual({ section: 'cli-agents' })
  })

  it('undefined when the last turn is not a fatal config failure', () => {
    expect(
      lastRecoveryTarget([
        { role: 'user', text: 'hi' },
        { role: 'assistant', text: 'session not found' },
      ]),
    ).toBeUndefined()
  })
})

describe('#499 detector accepts a stamped target (legacy rows keep working)', () => {
  it('message with fatal flag and target still counts as fatal', () => {
    expect(
      isFatalConfigErrorMessage({
        role: 'assistant',
        fatalConfigError: true,
        configTarget: { section: 'cli-agents' },
      }),
    ).toBe(true)
  })
})
