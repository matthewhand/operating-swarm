import { describe, expect, it } from 'vitest'
import { autoPickFor, type ComposerProviderOption } from '../composerPicker'

describe('#803 — auto-pick providers with <=1 option', () => {
  it('returns the pick for exactly 1 non-session option', () => {
    const one: ComposerProviderOption = { id: 'cli:codex', label: 'codex', kind: 'cli' }
    const only = { id: 'grok-4', label: 'grok-4', tag: 'model' as const }
    expect(autoPickFor(one, [only])).toEqual({ provider: one, option: only })
  })

  it('returns null for 0 options — the explicit Use-default accept is the contract (#681, #804)', () => {
    const zero: ComposerProviderOption = { id: 'cli:grok', label: 'grok', kind: 'cli' }
    expect(autoPickFor(zero, [])).toBeNull()
    const remote: ComposerProviderOption = { id: 'remote:tf', label: 'TrueForge', kind: 'remote' }
    expect(autoPickFor(remote, [])).toBeNull()
  })

  it('returns null when there are >= 2 options (stage 2 is worth showing)', () => {
    const many: ComposerProviderOption = { id: 'api', label: 'API gateway', kind: 'api' }
    const opts = [
      { id: 'a', label: 'A' },
      { id: 'b', label: 'B' },
    ]
    expect(autoPickFor(many, opts)).toBeNull()
  })

  it('never auto-picks a session-tagged option — the explicit click routes onResumeSession (#711)', () => {
    const cli: ComposerProviderOption = { id: 'cli:codex', label: 'codex', kind: 'cli' }
    const session = { id: 'codex:main', label: 'codex main session', tag: 'session' as const }
    expect(autoPickFor(cli, [session])).toBeNull()
    // Mixed bag with one model + one session still descends.
    expect(
      autoPickFor(cli, [session, { id: 'grok-4', label: 'grok-4', tag: 'model' as const }]),
    ).toBeNull()
  })

  it('never auto-picks while options are still loading (optionsPending) — partial lists lie', () => {
    // #711 race: sessions fetched when the picker opens; before they land a
    // CLI with sessions + models looks like a one-model provider.
    const cli: ComposerProviderOption = {
      id: 'cli:grok',
      label: 'grok',
      kind: 'cli',
      optionsPending: true,
    }
    expect(autoPickFor(cli, [])).toBeNull()
    expect(autoPickFor(cli, [{ id: 'grok-4', label: 'grok-4', tag: 'model' as const }])).toBeNull()
  })
})
