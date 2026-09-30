import { afterEach, describe, expect, it, vi } from 'vitest'
import type { CliAgentsInfo } from '../api'
import {
  HOST_CLI_TIP_PREF_KEY,
  HOST_CLI_TIP_STORAGE_KEY,
  hostCliDetectedName,
  hostCliTipBody,
  hostCliTipTitle,
  isHostCliTipDismissed,
  persistHostCliTipDismissedLocal,
  prefsHostCliTipDismissed,
  shouldShowHostCliTip,
} from '../hostCliTip'

function info(over: Partial<CliAgentsInfo> = {}): CliAgentsInfo {
  return {
    clis: ['claude', 'codex', 'opencode'],
    native_consensus: {},
    catalog: {},
    ...over,
  }
}

afterEach(() => {
  try {
    localStorage.removeItem(HOST_CLI_TIP_STORAGE_KEY)
  } catch {
    /* ignore */
  }
  vi.restoreAllMocks()
})

describe('hostCliDetectedName', () => {
  it('names a CLI found on PATH but not yet configured', () => {
    expect(
      hostCliDetectedName(info({ discovered: ['opencode'], configured: [] })),
    ).toBe('opencode')
  })

  it('is empty when nothing is on PATH (Success #4)', () => {
    expect(hostCliDetectedName(info({ discovered: [], configured: [] }))).toBe('')
    expect(hostCliDetectedName(info())).toBe('')
    expect(hostCliDetectedName(null)).toBe('')
    expect(hostCliDetectedName(undefined)).toBe('')
  })

  it('is empty once every detected CLI is configured', () => {
    expect(
      hostCliDetectedName(info({ discovered: ['opencode'], configured: ['opencode'] })),
    ).toBe('')
  })

  it('offers the first unconfigured CLI from a mixed set', () => {
    expect(
      hostCliDetectedName(
        info({ discovered: ['claude', 'codex', 'opencode'], configured: ['claude'] }),
      ),
    ).toBe('codex')
  })

  it('matches configured names case-insensitively', () => {
    expect(
      hostCliDetectedName(info({ discovered: ['OpenCode'], configured: ['opencode'] })),
    ).toBe('')
  })

  it('falls back to the installed alias on older payloads', () => {
    expect(hostCliDetectedName(info({ installed: ['pi'] }))).toBe('pi')
  })
})

describe('shouldShowHostCliTip', () => {
  it('shows when a CLI is detected and unconfigured', () => {
    expect(
      shouldShowHostCliTip({ info: info({ discovered: ['opencode'], configured: [] }) }),
    ).toBe(true)
  })

  it('never shows with no CLI on PATH (Success #4)', () => {
    expect(shouldShowHostCliTip({ info: info({ discovered: [] }) })).toBe(false)
    expect(shouldShowHostCliTip({})).toBe(false)
  })

  it('never shows once dismissed (Success #3)', () => {
    expect(
      shouldShowHostCliTip({
        info: info({ discovered: ['opencode'] }),
        dismissed: true,
      }),
    ).toBe(false)
  })
})

describe('copy', () => {
  it('states the CLI was detected without brand strings', () => {
    expect(hostCliTipTitle('opencode')).toBe('opencode detected')
    expect(hostCliTipBody('opencode')).toContain('opencode')
    const copy = `${hostCliTipTitle('opencode')} ${hostCliTipBody('opencode')}`
    expect(copy.toLowerCase()).not.toContain('grok bot')
  })
})

describe('dismissal persistence', () => {
  it('localStorage round-trips', () => {
    expect(isHostCliTipDismissed()).toBe(false)
    persistHostCliTipDismissedLocal()
    expect(isHostCliTipDismissed()).toBe(true)
  })

  it('reads the prefs extras bag', () => {
    expect(prefsHostCliTipDismissed({ values: {} })).toBe(false)
    expect(prefsHostCliTipDismissed({ values: { [HOST_CLI_TIP_PREF_KEY]: true } })).toBe(true)
  })
})
