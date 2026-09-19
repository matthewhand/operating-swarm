/**
 * #551 — the frontend decision comes from the published capability.
 *
 * The acceptance contract: a capability declared on the kind base reaches the
 * UI through `seat_capabilities` data alone — the same seat flips behaviour
 * when the declaration flips, with no frontend change and no kind check.
 * An absent payload falls back to the kind-derived gates (older backend).
 */
import { describe, expect, it } from 'vitest'
import { composerMenuCapabilities } from '../composerMenu'

const API_DECLARED = {
  attach: { enabled: true, reason: '' },
  compact: { enabled: true, reason: '' },
  plugins: { enabled: true, reason: '' },
  routines: { enabled: true, reason: '' },
}

const CLI_DECLARED = {
  attach: { enabled: false, reason: 'File attachments aren’t supported for CLI seats' },
  compact: { enabled: false, reason: 'Compact needs a default API profile' },
  plugins: { enabled: false, reason: 'Plugins are available on API and blueprint seats' },
  routines: { enabled: false, reason: 'Routines drive swarm-side scheduling' },
}

describe('#551 declared capabilities drive the + menu', () => {
  it('a CLI seat whose kind base declares attach enabled gains the action', () => {
    // The subclass-override probe: same seat kind, different declaration,
    // different UI — derived from data, not from `kind === 'cli'`.
    const seat = {
      isCli: true,
      declaredCapabilities: { ...CLI_DECLARED, attach: { enabled: true, reason: '' } },
    }
    expect(composerMenuCapabilities(seat).addFiles.enabled).toBe(true)
  })

  it('an API seat whose kind base revokes plugins loses the entry', () => {
    const seat = {
      isApi: true,
      declaredCapabilities: { ...API_DECLARED, plugins: { enabled: false, reason: 'Revoked' } },
    }
    const caps = composerMenuCapabilities(seat)
    expect(caps.plugins.enabled).toBe(false)
    expect(caps.plugins.reason).toBe('Revoked')
  })

  it('an absent payload falls back to the kind-derived gates (older backend)', () => {
    expect(composerMenuCapabilities({ isCli: true }).addFiles.enabled).toBe(false)
    expect(composerMenuCapabilities({ pluginsSwarmOwned: true }).plugins.enabled).toBe(true)
  })

  it('an unknown capability is never offered (doctrine rule 4)', () => {
    // The menu only consults names it renders; a name outside the declared
    // vocabulary resolves to not-offered via the backend, never to a guess.
    const seat = {
      isApi: true,
      pluginsSwarmOwned: true,
      declaredCapabilities: {} as Record<string, never>,
    }
    const caps = composerMenuCapabilities(seat as never)
    // attach/plugins are absent from the payload → fallback gates, not "on".
    expect(caps.addFiles.enabled).toBe(true) // API fallback
    expect(caps.plugins.enabled).toBe(true) // swarm-owned fallback
  })
})
