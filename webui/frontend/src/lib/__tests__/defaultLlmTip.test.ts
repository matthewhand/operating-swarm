import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  DEFAULT_LLM_TIP_PREF_KEY,
  DEFAULT_LLM_TIP_STORAGE_KEY,
  isDefaultLlmTipDismissed,
  persistDefaultLlmTipDismissedLocal,
  prefsDefaultLlmTipDismissed,
  shouldShowDefaultLlmTip,
} from '../defaultLlmTip'

afterEach(() => {
  try {
    localStorage.removeItem(DEFAULT_LLM_TIP_STORAGE_KEY)
  } catch {
    /* ignore */
  }
  vi.restoreAllMocks()
})

describe('shouldShowDefaultLlmTip', () => {
  const base = { isApiAgent: true, defaultLlmReady: false } as const

  it('shows for API seats when the default LLM is not ready', () => {
    expect(shouldShowDefaultLlmTip(base)).toBe(true)
  })

  it('never shows for non-API seats (cli/remote/team)', () => {
    expect(shouldShowDefaultLlmTip({ ...base, isApiAgent: false })).toBe(false)
  })

  it('never shows when dismissed', () => {
    expect(shouldShowDefaultLlmTip({ ...base, dismissed: true })).toBe(false)
  })

  it('never shows when the default LLM is ready or unknown', () => {
    expect(shouldShowDefaultLlmTip({ ...base, defaultLlmReady: true })).toBe(false)
    expect(shouldShowDefaultLlmTip({ ...base, defaultLlmReady: undefined })).toBe(false)
  })

  it('exempts seats with an explicit model/profile override', () => {
    expect(
      shouldShowDefaultLlmTip({ ...base, hasExplicitModelOverride: true }),
    ).toBe(false)
  })
})

describe('dismissal persistence', () => {
  it('localStorage round-trips', () => {
    expect(isDefaultLlmTipDismissed()).toBe(false)
    persistDefaultLlmTipDismissedLocal()
    expect(isDefaultLlmTipDismissed()).toBe(true)
  })

  it('reads the prefs extras bag', () => {
    expect(prefsDefaultLlmTipDismissed({ values: {} })).toBe(false)
    expect(prefsDefaultLlmTipDismissed({ values: { [DEFAULT_LLM_TIP_PREF_KEY]: true } })).toBe(true)
  })
})
