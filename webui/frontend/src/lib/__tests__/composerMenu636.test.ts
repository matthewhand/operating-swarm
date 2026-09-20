/**
 * #636 — Compact gating per seat kind.
 *
 * API seats: unchanged. CLI seats: enabled when a default API is configured
 * (`defaultLlmReady`) OR the provider declares a native `cli_compact` hook;
 * otherwise visible-but-greyed with a reason that names the missing API.
 * Remote seats: unchanged (disabled).
 */
import { describe, expect, it } from 'vitest'
import { composerMenuCapabilities } from '../composerMenu'

describe('#636 CLI compact gating', () => {
  it('API seats keep Compact enabled exactly as before', () => {
    expect(composerMenuCapabilities({ isApi: true }).compact.enabled).toBe(true)
  })

  it('a CLI seat with a configured default API gets Compact', () => {
    const menu = composerMenuCapabilities({ isCli: true, defaultLlmReady: true })
    expect(menu.compact.enabled).toBe(true)
  })

  it('a CLI seat with a provider-native compact hook gets Compact without an API', () => {
    const menu = composerMenuCapabilities({ isCli: true, cliCompactCapable: true })
    expect(menu.compact.enabled).toBe(true)
  })

  it('a CLI seat with neither stays disabled and the reason names the API', () => {
    const menu = composerMenuCapabilities({ isCli: true })
    expect(menu.compact.enabled).toBe(false)
    expect(menu.compact.reason).toMatch(/no api is configured/i)
  })

  it('remote seats stay disabled', () => {
    const menu = composerMenuCapabilities({
      isRemote: true,
      defaultLlmReady: true,
    })
    expect(menu.compact.enabled).toBe(false)
  })

  it('#830: a disabled remote reason names the PROVIDER, not the kind', () => {
    const menu = composerMenuCapabilities({ isRemote: true, providerName: 'Herdr' })
    expect(menu.compact.enabled).toBe(false)
    expect(menu.compact.reason).toBe('Compact is not implemented for Herdr')
  })

  it('#830: unknown provider falls back to "this provider"', () => {
    expect(composerMenuCapabilities({ isRemote: true }).compact.reason).toBe(
      'Compact is not implemented for this provider',
    )
  })

  it('#830: a remote declaring compact capability gains the action', () => {
    const menu = composerMenuCapabilities({
      isRemote: true,
      providerName: 'TrueForge',
      remoteCompactCapable: true,
    })
    expect(menu.compact.enabled).toBe(true)
  })

  it('an unresolved seat never gains Compact (positive isApi gate kept)', () => {
    expect(
      composerMenuCapabilities({ defaultLlmReady: true }).compact.enabled,
    ).toBe(false)
  })
})
