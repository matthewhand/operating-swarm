import { describe, expect, it } from 'vitest'
import {
  CLI_SESSION_RECOVERY_MESSAGE,
  isFatalConfigErrorMessage,
  isFatalConfigErrorText,
  lastTurnNeedsRecovery,
} from '../cliSessionRecovery'

describe('cliSessionRecovery', () => {
  it('classifies unconfigured CLI copy as fatal', () => {
    expect(
      isFatalConfigErrorText(
        "No CLI agents are configured. Add a 'cli_agents' block to your swarm config.",
      ),
    ).toBe(true)
  })

  it('classifies resume failures as fatal', () => {
    expect(isFatalConfigErrorText('[grok] failed: session not found')).toBe(true)
    expect(isFatalConfigErrorText('Cannot resume expired session')).toBe(true)
  })

  it('classifies unconfigured harness copy as fatal', () => {
    expect(isFatalConfigErrorText('Remote harness endpoint not configured yet')).toBe(true)
    expect(isFatalConfigErrorText('ssh harness not configured')).toBe(true)
  })

  it('does not treat transient model errors as fatal config', () => {
    expect(isFatalConfigErrorText('Error: the model returned no usable text')).toBe(false)
    expect(isFatalConfigErrorText('rate limit exceeded, retry later')).toBe(false)
    expect(isFatalConfigErrorMessage({ role: 'assistant', text: 'hello' })).toBe(false)
  })

  it('honours stored fatal_config_error metadata', () => {
    expect(
      isFatalConfigErrorMessage({
        role: 'assistant',
        text: 'something generic',
        fatal_config_error: true,
      }),
    ).toBe(true)
    expect(
      isFatalConfigErrorMessage({
        role: 'assistant',
        text: 'something generic',
        fatalConfigError: true,
      }),
    ).toBe(true)
  })

  it('shows recovery only when the last turn is a terminal assistant failure', () => {
    expect(
      lastTurnNeedsRecovery([
        { role: 'user', text: 'hi' },
        { role: 'assistant', text: 'No CLI agents are configured.' },
      ]),
    ).toBe(true)
    expect(
      lastTurnNeedsRecovery([
        { role: 'user', text: 'hi' },
        { role: 'assistant', text: 'No CLI agents are configured.' },
        { role: 'user', text: 'try again' },
      ]),
    ).toBe(false)
    expect(
      lastTurnNeedsRecovery([
        { role: 'user', text: 'hi' },
        { role: 'assistant', text: 'ok' },
      ]),
    ).toBe(false)
    expect(lastTurnNeedsRecovery([])).toBe(false)
  })

  it('keeps the recovery copy stable', () => {
    expect(CLI_SESSION_RECOVERY_MESSAGE).toBe(
      'This session encountered an agent configuration error.',
    )
  })
})
