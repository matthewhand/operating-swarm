/**
 * #1220 — the composer `+` menu's rewrite capability.
 *
 * Doctrine (this is the pin the dock renders from):
 * 1. rewrite ships DISABLED for every seat — the aux-LLM spend must be a
 *    deliberate operator opt-in, not a default;
 * 2. disabled means ABSENT (the dock renders nothing), not greyed — there
 *    is no seat state that can flip it back on, so a reason row would lie;
 * 3. the operator preference (`swarm_composer_rewrite_enabled`) lights it
 *    up for any seat kind — rewriting a prompt is not seat-kind-specific;
 * 4. a #551 declared capability outranks the preference, same as plugins.
 */
import { describe, expect, it } from 'vitest'
import {
  COMPOSER_MENU_ITEM_IDS,
  composerMenuCapabilities,
} from '../composerMenu'

describe('#1220 rewrite capability', () => {
  it('rewrite is a declared member of the item-id union', () => {
    expect(COMPOSER_MENU_ITEM_IDS).toContain('rewrite')
  })

  it('ships disabled for every seat kind', () => {
    for (const seat of [
      { isApi: true },
      { isCli: true },
      { isRemote: true },
      {},
    ]) {
      const menu = composerMenuCapabilities(seat)
      expect(menu.rewrite.enabled).toBe(false)
      expect(menu.rewrite.reason).toContain('Settings')
    }
  })

  it('the operator opt-in lights it up regardless of seat kind', () => {
    for (const seat of [
      { isApi: true, rewriteEnabled: true },
      { isCli: true, rewriteEnabled: true },
      { isRemote: true, rewriteEnabled: true },
    ]) {
      expect(composerMenuCapabilities(seat).rewrite.enabled).toBe(true)
    }
  })

  it('no rewriteEnabled flag means off even on an API seat (default-off)', () => {
    expect(composerMenuCapabilities({ isApi: true }).rewrite.enabled).toBe(false)
  })

  it('a #551 declared capability outranks the operator preference', () => {
    const menu = composerMenuCapabilities({
      isApi: true,
      rewriteEnabled: false,
      declaredCapabilities: { rewrite: { enabled: true, reason: '' } },
    })
    expect(menu.rewrite.enabled).toBe(true)
    const off = composerMenuCapabilities({
      isApi: true,
      rewriteEnabled: true,
      declaredCapabilities: { rewrite: { enabled: false, reason: 'declared off' } },
    })
    expect(off.rewrite.enabled).toBe(false)
  })
})
