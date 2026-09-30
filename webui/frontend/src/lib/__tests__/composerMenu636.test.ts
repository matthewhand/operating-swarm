/**
 * #1230 — Compact is API-only.
 *
 * Supersedes the #636 CLI-seat gating: a CLI seat no longer gains Compact
 * from a configured default API or a provider `cli_compact` hook, and a remote
 * seat no longer gains it from `remoteCompactCapable`. Every non-API seat
 * carries `enabled: false`, which the dock renders as ABSENT — never as a
 * disabled/"not available" control.
 */
import { describe, expect, it } from 'vitest'
import { composerMenuCapabilities } from '../composerMenu'

describe('#1230 Compact is API-only', () => {
  it('API seats keep Compact enabled', () => {
    expect(composerMenuCapabilities({ isApi: true }).compact.enabled).toBe(true)
  })

  it('a CLI seat does NOT gain Compact from a configured default API', () => {
    // #1725: `defaultLlmReady` is gone from the seat shape, so this is the
    // strongest surviving form of the control — see the last test, which proves
    // Compact is gated on `isApi` alone and no other input can reach it.
    const menu = composerMenuCapabilities({ isCli: true })
    expect(menu.compact.enabled).toBe(false)
  })

  it('a CLI seat does NOT gain Compact from a provider-native compact hook', () => {
    const menu = composerMenuCapabilities({ isCli: true, cliCompactCapable: true })
    expect(menu.compact.enabled).toBe(false)
  })

  it('a CLI seat reason names the API-only scope (never rendered, but pinned)', () => {
    const menu = composerMenuCapabilities({ isCli: true })
    expect(menu.compact.enabled).toBe(false)
    expect(menu.compact.reason).toMatch(/api-only/i)
  })

  it('remote seats never gain Compact, even with a provider hook', () => {
    const menu = composerMenuCapabilities({
      isRemote: true,
      providerName: 'TrueForge',
      remoteCompactCapable: true,
    })
    expect(menu.compact.enabled).toBe(false)
  })

  it('an unresolved seat never gains Compact (positive isApi gate kept)', () => {
    // #1725: the strongest form of this negative control. Compact is the one
    // capability with no derived gate at all — it is `Boolean(seat.isApi)` and
    // nothing else, so *no* combination of the other declared inputs can flip
    // it. Asserted on the full declared input set rather than on a single
    // removed field, so deleting a field cannot quietly weaken the test.
    const everyInputButIsApi = {
      isCli: false,
      isRemote: false,
      cliCompactCapable: true,
      remoteCompactCapable: true,
      pluginsSwarmOwned: true,
      rewriteEnabled: true,
      declaredCapabilities: {
        compact: { enabled: true, reason: '' },
        plugins: { enabled: true, reason: '' },
        attach: { enabled: true, reason: '' },
        rewrite: { enabled: true, reason: '' },
      },
    } as const
    expect(composerMenuCapabilities(everyInputButIsApi).compact.enabled).toBe(false)
    // …and the positive control still holds with those same inputs.
    expect(
      composerMenuCapabilities({ ...everyInputButIsApi, isApi: true }).compact.enabled,
    ).toBe(true)
  })
})
