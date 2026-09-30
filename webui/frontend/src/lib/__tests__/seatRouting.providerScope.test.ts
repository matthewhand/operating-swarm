/**
 * #1352/#1353/#1356 — provider scoping helpers.
 *
 * The provider scope of an agent is its Edit-agent inference override when one
 * exists, otherwise its own declared kind/provider id. The default inference
 * profile is never consulted. `filterCliModels` keeps CLI model ids in their
 * own namespace, dropping foreign API / LiteLLM profile ids (#1356).
 */
import { describe, expect, it } from 'vitest'
import {
  filterAgentsByProviderScope,
  providerScopeForAgent,
  providerScopeFromInference,
  providerScopeKey,
} from '../seatRouting'
import { filterCliModels } from '../composerPicker'

describe('#1352 provider scope derivation', () => {
  it('prefers the Edit-agent inference override', () => {
    const scope = providerScopeForAgent({
      id: 'cli_agent',
      kind: 'cli',
      providerId: 'codex',
      inference: { id: 'opencode', kind: 'cli' },
    })
    expect(scope).toEqual({ kind: 'cli', id: 'opencode' })
    expect(providerScopeKey(scope!)).toBe('cli:opencode')
  })

  it('falls back to the row’s own kind/provider id when there is no override', () => {
    expect(
      providerScopeKey(
        providerScopeForAgent({ id: 'cli_agent', kind: 'cli', providerId: 'codex' })!,
      ),
    ).toBe('cli:codex')
    expect(
      providerScopeKey(providerScopeForAgent({ id: 'codey', kind: 'api' })!),
    ).toBe('api:api')
    expect(
      providerScopeKey(
        providerScopeForAgent({ id: 'hermes', kind: 'remote', providerId: 'hermes' })!,
      ),
    ).toBe('remote:hermes')
  })

  it('normalizes inference kinds (llm → API gateway, herdr → remote)', () => {
    // An llm inference seat is the API gateway — the profile is the model
    // dimension, not a provider key (and never the default profile).
    expect(providerScopeFromInference({ id: 'orchestration', kind: 'llm' })).toEqual({
      kind: 'api',
      id: 'api',
    })
    expect(providerScopeFromInference({ id: 'dev', kind: 'herdr' })).toEqual({
      kind: 'remote',
      id: 'dev',
    })
    expect(providerScopeFromInference(null)).toBeNull()
    expect(providerScopeFromInference({ id: '', kind: 'cli' })).toBeNull()
  })

  it('filters agents to one provider, keeping all when no scope/rows declare one', () => {
    const rows = [
      { id: 'a', provider: 'cli:opencode' },
      { id: 'b', provider: 'cli:codex' },
      { id: 'c', provider: 'api:api' },
    ]
    expect(filterAgentsByProviderScope(rows, 'cli:opencode').map((r) => r.id)).toEqual(['a'])
    expect(filterAgentsByProviderScope(rows, null).map((r) => r.id)).toEqual([
      'a',
      'b',
      'c',
    ])
    // No row declares a provider → nothing to filter on (back-compat).
    const bare: Array<{ id: string; provider?: string }> = [{ id: 'a' }, { id: 'b' }]
    expect(filterAgentsByProviderScope(bare, 'cli:opencode').map((r) => r.id)).toEqual([
      'a',
      'b',
    ])
  })
})

describe('#1356 filterCliModels namespace guard', () => {
  it('drops foreign API/LiteLLM profile ids and keeps the CLI’s own models', () => {
    const foreign = new Set(['litellm/orchestration', 'anthropic/claude-sonnet-4-6'])
    expect(
      filterCliModels(
        ['opencode-go/x', 'litellm/orchestration', 'opencode-go/y', 'anthropic/claude-sonnet-4-6'],
        foreign,
      ),
    ).toEqual(['opencode-go/x', 'opencode-go/y'])
  })

  it('dedupes/trims and is a no-op with no foreign set', () => {
    expect(filterCliModels([' a ', 'a', 'b'], new Set())).toEqual([' a ', 'a', 'b'])
    expect(filterCliModels(['a', 'a', 'b'], new Set(['b']))).toEqual(['a'])
  })
})
