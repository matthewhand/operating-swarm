/**
 * #1215 / #1219 / #1220 — the composer affordances preference module.
 *
 * Pins the resolution doctrine before any UI wires it up:
 *
 * 1. Provider dropdown per viewport tier (#1219): mobile ships HIDDEN,
 *    tablet/desktop keep #878's visible default. An explicit per-tier
 *    override always wins; #878's legacy boolean migrates on first read.
 * 2. AI prompt rewrite (#1220): disabled by default, single boolean,
 *    opt-in — no aux-LLM path may run when it is off.
 */
import { describe, expect, it, beforeEach, vi } from 'vitest'
import {
  COMPOSER_REWRITE_ENABLED_KEY,
  COMPOSER_SHOW_PROVIDER_TIERS_KEY,
  DEFAULT_SHOW_PROVIDER_TIERS,
  currentShowProviderResolved,
  loadRewriteEnabled,
  loadShowProviderTiers,
  saveRewriteEnabled,
  saveShowProviderTiers,
} from '../composerAffordances'
import { COMPOSER_SHOW_PROVIDER_STORAGE_KEY } from '../composerShowProvider'

describe('#1219 provider dropdown per viewport tier', () => {
  beforeEach(() => localStorage.clear())

  it('ships mobile hidden, tablet/desktop visible', () => {
    expect(DEFAULT_SHOW_PROVIDER_TIERS).toEqual({ mobile: false, tablet: true, desktop: true })
    expect(loadShowProviderTiers()).toEqual(DEFAULT_SHOW_PROVIDER_TIERS)
  })

  it('resolves for the tier the user is actually in', () => {
    expect(currentShowProviderResolved('mobile')).toBe(false)
    expect(currentShowProviderResolved('tablet')).toBe(true)
    expect(currentShowProviderResolved('desktop')).toBe(true)
  })

  it('an explicit tier override wins over the shipped default', () => {
    saveShowProviderTiers({ mobile: true, tablet: true, desktop: true })
    expect(currentShowProviderResolved('mobile')).toBe(true)
    saveShowProviderTiers({ mobile: false, tablet: false, desktop: false })
    expect(currentShowProviderResolved('desktop')).toBe(false)
  })

  it('migrates the #878 legacy boolean instead of ignoring it', () => {
    localStorage.setItem(COMPOSER_SHOW_PROVIDER_STORAGE_KEY, 'false')
    expect(loadShowProviderTiers()).toEqual({ mobile: false, tablet: false, desktop: false })
    localStorage.setItem(COMPOSER_SHOW_PROVIDER_STORAGE_KEY, 'true')
    expect(loadShowProviderTiers()).toEqual({ mobile: true, tablet: true, desktop: true })
  })

  it('partial stored overrides keep other tiers at their defaults', () => {
    localStorage.setItem(
      COMPOSER_SHOW_PROVIDER_TIERS_KEY,
      JSON.stringify({ mobile: true }),
    )
    const pref = loadShowProviderTiers()
    expect(pref.mobile).toBe(true)
    expect(pref.tablet).toBe(true) // default
    expect(pref.desktop).toBe(true) // default
  })

  it('save dispatches the change event so open screens react live', () => {
    const listener = vi.fn()
    window.addEventListener('swarm:set-composer-show-provider-tiers', listener)
    saveShowProviderTiers({ mobile: true, tablet: true, desktop: true })
    expect(listener).toHaveBeenCalledOnce()
    window.removeEventListener('swarm:set-composer-show-provider-tiers', listener)
  })
})

describe('#1220 AI prompt rewrite opt-in', () => {
  beforeEach(() => localStorage.clear())

  it('is disabled by default — no rewrite affordance without explicit opt-in', () => {
    expect(loadRewriteEnabled()).toBe(false)
  })

  it('persists the opt-in and dispatches the change event', () => {
    const listener = vi.fn()
    window.addEventListener('swarm:set-composer-rewrite-enabled', listener)
    expect(saveRewriteEnabled(true)).toBe(true)
    expect(localStorage.getItem(COMPOSER_REWRITE_ENABLED_KEY)).toBe('true')
    expect(loadRewriteEnabled()).toBe(true)
    expect(listener).toHaveBeenCalledOnce()
    window.removeEventListener('swarm:set-composer-rewrite-enabled', listener)
  })
})
