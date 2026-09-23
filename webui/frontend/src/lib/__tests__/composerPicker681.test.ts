/**
 * #681 — the two-stage composer picker's state machine.
 *
 * Stage 1 lists *providers* (API gateway, CLI, remote framework, team — the
 * cross-kind rows keep their declared kind). Picking one descends to stage 2,
 * which always offers "accept the provider's default" before any specific
 * option. Esc backs out exactly one stage; back from stage 1 means close.
 * Pure and testable — the dialog component only renders what this returns.
 */
import { describe, expect, it } from 'vitest'
import {
  backOneStage,
  filterProviders,
  initialComposerPickerState,
  pickProvider,
  stage2Rows,
  type ComposerProviderOption,
} from '../composerPicker'

const providers: ComposerProviderOption[] = [
  { id: 'api', label: 'API gateway', kind: 'api', defaultOptionId: 'prof-default' },
  { id: 'cli:codex', label: 'codex', kind: 'cli', defaultOptionId: 'cli:codex:main' },
  { id: 'remote:openmousbot', label: 'openmousbot', kind: 'remote' },
  { id: 'team:demo', label: 'demo team', kind: 'team', defaultOptionId: 'team:demo:planner' },
]

describe('#681 stage 1 — provider filtering', () => {
  it('starts at the provider stage with no query', () => {
    const s = initialComposerPickerState()
    expect(s.stage).toBe('providers')
    expect(s.query).toBe('')
    expect(s.provider).toBeNull()
  })

  it('filters providers by label or id, case-insensitively', () => {
    expect(filterProviders(providers, 'codex').map((p) => p.id)).toEqual(['cli:codex'])
    expect(filterProviders(providers, 'REMOTE').map((p) => p.id)).toEqual(['remote:openmousbot'])
    expect(filterProviders(providers, 'demo').map((p) => p.id)).toEqual(['team:demo'])
    expect(filterProviders(providers, 'zzz')).toEqual([])
  })

  it('empty query shows every provider', () => {
    expect(filterProviders(providers, '')).toHaveLength(4)
  })
})

describe('#681 stage transition', () => {
  it('descending to a provider resets the query and lands on options', () => {
    const s = pickProvider({ ...initialComposerPickerState(), query: 'codex' }, providers[1])
    expect(s).not.toBeNull()
    expect(s.stage).toBe('options')
    expect(s.provider?.id).toBe('cli:codex')
    expect(s.query).toBe('')
  })
})

describe('#681 stage 2 — accept default first', () => {
  it('lists the Use-default row before any specific option', () => {
    const rows = stage2Rows(providers[0], [
      { id: 'prof-a', label: 'Profile A' },
      { id: 'prof-default', label: 'Default profile' },
    ])
    expect(rows[0]).toMatchObject({ row: 'default', id: 'prof-default' })
    expect(rows.map((r) => r.id)).toContain('prof-a')
    expect(rows[0].label).toContain('Use default')
  })

  it('a provider without a declared default still offers Use default (empty id = provider fallback)', () => {
    const rows = stage2Rows(providers[2], [{ id: 'bot-1', label: 'Bot 1' }])
    expect(rows[0]).toEqual({ row: 'default', id: '', label: 'Use default' })
  })

  it('the default row survives any query; specific options filter', () => {
    const options = [
      { id: 'm-fast', label: 'fast model' },
      { id: 'm-smart', label: 'smart model' },
    ]
    const rows = stage2Rows(providers[0], options, 'smart')
    expect(rows).toHaveLength(2)
    expect(rows[0].row).toBe('default')
    expect(rows[1]).toMatchObject({ id: 'm-smart' })
  })
})

describe('#681 esc backs out exactly one stage', () => {
  it('from options → providers (provider cleared, query reset)', () => {
    const s = backOneStage(pickProvider(initialComposerPickerState(), providers[0]))
    expect(s).not.toBeNull()
    expect(s!.stage).toBe('providers')
    expect(s!.provider).toBeNull()
    expect(s!.query).toBe('')
  })

  it('from providers → null, meaning the caller closes the dialog', () => {
    expect(backOneStage(initialComposerPickerState())).toBeNull()
  })
})
