import { afterEach, describe, expect, it } from 'vitest'
import {
  AGENT_REMOTE_BINDINGS_KEY,
  isRemoteKindAgent,
  loadAgentRemoteBinding,
  remotesListForSelect,
  resolveBoundRemoteId,
  saveAgentRemoteBinding,
} from '../agentRemote'
import { configuredRemotes, remoteSelectPlaceholder } from '../remotes'
import { STARTER_REMOTE_ID } from '../starter-agents'

const OMB = {
  id: 'omb',
  kind: 'omb',
  label: 'OpenMousBot',
  title: 'OpenMousBot',
  host_label: '',
  base_url: 'http://127.0.0.1:8802',
  source: 'config',
}

describe('agentRemote binding (Issue #745)', () => {
  afterEach(() => {
    localStorage.removeItem(AGENT_REMOTE_BINDINGS_KEY)
  })

  it('persists id+kind and clears on empty', () => {
    expect(loadAgentRemoteBinding('starter-remote')).toBeNull()
    expect(saveAgentRemoteBinding('starter-remote', { id: 'omb', kind: 'omb' })).toEqual({
      id: 'omb',
      kind: 'omb',
    })
    expect(loadAgentRemoteBinding('starter-remote')).toEqual({ id: 'omb', kind: 'omb' })
    expect(JSON.parse(localStorage.getItem(AGENT_REMOTE_BINDINGS_KEY) || '{}')).toEqual({
      'starter-remote': { id: 'omb', kind: 'omb' },
    })
    saveAgentRemoteBinding('starter-remote', null)
    expect(loadAgentRemoteBinding('starter-remote')).toBeNull()
  })

  it('resolves URL remotes as the view when no binding exists (#502: binding wins first)', () => {
    expect(
      resolveBoundRemoteId({
        remoteFromUrl: 'omb',
        persisted: null,
        configuredIds: ['omb'],
      }),
    ).toBe('omb')
  })

  it('returns empty for stale persisted ids when remotes exist', () => {
    expect(
      resolveBoundRemoteId({
        persisted: { id: 'gone', kind: 'hermes' },
        configuredIds: ['omb'],
      }),
    ).toBe('')
  })

  it('keeps a live persisted binding', () => {
    expect(
      resolveBoundRemoteId({
        persisted: { id: 'omb', kind: 'omb' },
        configuredIds: ['omb', 'hermes'],
      }),
    ).toBe('omb')
  })

  it('injects a bound remote into the select catalog', () => {
    const catalog = remotesListForSelect(
      { object: 'list', kinds: [], configured: [] },
      [],
      { id: 'omb', kind: 'omb', title: 'OpenMousBot' },
    )
    expect(configuredRemotes(catalog).map((row) => row.id)).toEqual(['omb'])
    expect(catalog.configured?.[0]?.kind).toBe('omb')
  })

  it('merges Settings configured remotes without treating a rail array as empty', () => {
    const catalog = remotesListForSelect({ object: 'list', configured: [OMB] }, [
      { id: 'omb', kind: 'omb', title: 'OpenMousBot', configured: true, agents: [] },
    ])
    expect(configuredRemotes(catalog)).toHaveLength(1)
    expect(remoteSelectPlaceholder(configuredRemotes(catalog).length, 'omb')).toBe('Remote')
    expect(remoteSelectPlaceholder(1, '')).toBe('default')
    expect(remoteSelectPlaceholder(0, '')).toBe('No remotes')
  })

  it('recognizes remote-kind agents including the starter seat', () => {
    expect(isRemoteKindAgent({ remoteFromUrl: 'omb' })).toBe(true)
    expect(isRemoteKindAgent({ blueprintId: STARTER_REMOTE_ID })).toBe(true)
    expect(isRemoteKindAgent({ selectedKind: 'remote' })).toBe(true)
    expect(isRemoteKindAgent({ blueprintId: 'codey' })).toBe(false)
    expect(isRemoteKindAgent({ blueprintId: 'cli:grok', agentKind: 'cli' })).toBe(false)
  })
})
