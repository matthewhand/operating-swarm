
import { describe, expect, it } from 'vitest'
import { autoPickFor, type ComposerProviderOption } from '../composerPicker'

describe('#803 — auto-pick providers with <=1 option', () => {
  it('returns the pick for 0 options (provider default) and 1 option', () => {
    const zero: ComposerProviderOption = { id: 'cli:grok', label: 'grok', kind: 'cli' }
    expect(autoPickFor(zero, [])).toEqual({ provider: zero, option: null })
    const one: ComposerProviderOption = { id: 'cli:codex', label: 'codex', kind: 'cli' }
    const only = { id: 'grok-4', label: 'grok-4', tag: 'model' as const }
    expect(autoPickFor(one, [only])).toEqual({ provider: one, option: only })
  })

  it('returns null when there are >= 2 options (stage 2 is worth showing)', () => {
    const many: ComposerProviderOption = { id: 'api', label: 'API gateway', kind: 'api' }
    const opts = [
      { id: 'a', label: 'A' },
      { id: 'b', label: 'B' },
    ]
    expect(autoPickFor(many, opts)).toBeNull()
  })

  it('ignores the synthetic default — the default IS the auto-pick for 0 options', () => {
    // stage2Rows always prepends a default row; autoPickFor counts real
    // options only.
    const remote: ComposerProviderOption = { id: 'remote:tf', label: 'TrueForge', kind: 'remote' }
    expect(autoPickFor(remote, [])).toEqual({ provider: remote, option: null })
  })
})
