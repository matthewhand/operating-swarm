import { describe, expect, it } from 'vitest'
import {
  addAgentRemoteImpls,
  configuredRemotes,
  herdrLocationLabel,
  isHerdrKind,
  remoteKindLabel,
  remoteKinds,
  remoteSelectPlaceholder,
  unusedRemoteKinds,
} from '../remotes'

describe('remotes catalog (REQ-59)', () => {
  it('labels omb as OpenMousBot and never OMB', () => {
    expect(remoteKindLabel('omb')).toBe('OpenMousBot')
    expect(remoteKindLabel('openmousbot')).toBe('OpenMousBot')
    expect(remoteKindLabel('hermes')).toBe('Hermes')
    expect(remoteKindLabel('open-swarm')).toBe('open-swarm')
    expect(remoteKindLabel('omb')).not.toMatch(/\bOMB\b/)
  })

  it('treats an empty catalog as no configured remotes', () => {
    const empty = {
      object: 'list' as const,
      kinds: [
        { id: 'hermes', label: 'Hermes' },
        { id: 'omb', label: 'OpenMousBot' },
        { id: 'rakazo', label: 'Rakazo' },
      ],
      configured: [],
      data: [],
    }
    expect(configuredRemotes(empty)).toEqual([])
    expect(unusedRemoteKinds(empty).map((kind) => kind.id)).toEqual([
      'hermes',
      'omb',
      'rakazo',
    ])
    expect(remoteKinds(empty).find((kind) => kind.id === 'omb')?.label).toBe('OpenMousBot')
  })

  it('lists only configured remotes after add', () => {
    const listed = {
      object: 'list' as const,
      kinds: [
        { id: 'hermes', label: 'Hermes' },
        { id: 'omb', label: 'OpenMousBot' },
        { id: 'rakazo', label: 'Rakazo' },
      ],
      configured: [
        {
          id: 'omb',
          kind: 'omb',
          label: 'OpenMousBot',
          title: 'OpenMousBot',
          host_label: '',
          base_url: 'http://127.0.0.1:8802',
          source: 'config',
        },
      ],
    }
    const rows = configuredRemotes(listed)
    expect(rows).toHaveLength(1)
    expect(rows[0].id).toBe('omb')
    expect(remoteKindLabel(rows[0].id, listed.kinds)).toBe('OpenMousBot')
    expect(unusedRemoteKinds(listed).map((kind) => kind.id)).toEqual(['hermes', 'rakazo'])
  })

  it('ignores default data rows when configured is omitted', () => {
    const listed = {
      object: 'list' as const,
      data: [
        {
          id: 'hermes',
          title: 'Hermes',
          host_label: '',
          base_url: 'http://198.51.100.36:8642',
          source: 'default',
        },
      ],
    }
    expect(configuredRemotes(listed)).toEqual([])
  })

  it('treats a configured array payload as remotes, not an empty catalog', () => {
    const rows = configuredRemotes([
      {
        id: 'omb',
        kind: 'omb',
        label: 'OpenMousBot',
        title: 'OpenMousBot',
        host_label: '',
        base_url: 'http://127.0.0.1:8802',
        source: 'config',
      },
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0].id).toBe('omb')
    expect(remoteSelectPlaceholder(rows.length, '')).toBe('Pick a remote')
    expect(remoteSelectPlaceholder(0, '')).toBe('No remotes')
  })

  it('Add-agent Remote impls stay under kind=remote (REQ-203)', () => {
    const impls = addAgentRemoteImpls({
      object: 'list',
      kinds: [{ id: 'omb', label: 'OpenMousBot' }],
      configured: [],
    })
    const ids = impls.map((kind) => kind.id)
    expect(ids).toContain('hermes')
    expect(ids).toContain('omb')
    expect(ids).toContain('rakazo')
    expect(ids).toContain('herdr')
    expect(impls.every((kind) => kind.kind === 'remote')).toBe(true)
    expect(impls.find((kind) => kind.id === 'herdr')?.impl).toBe('herdr')
  })

  it('labels Herdr as local vs SSH (REQ-100)', () => {
    expect(isHerdrKind('herdr')).toBe(true)
    expect(isHerdrKind('omb')).toBe(false)
    expect(herdrLocationLabel({ herdr_mode: 'local', base_url: '' })).toBe('Local Herdr (no SSH)')
    expect(
      herdrLocationLabel({
        herdr_mode: 'ssh',
        ssh_user: 'herdr',
        ssh_host: 'herdr.example.test',
        ssh_port: 22,
      }),
    ).toBe('SSH herdr@herdr.example.test')
  })
})
