import { describe, expect, it, vi, afterEach } from 'vitest'
import {
  OPENMOUSBOT_LABEL,
  fetchConfiguredRemotes,
  parseRailRemotes,
  remoteDisplayName,
} from '../remotesCatalog'

describe('remotesCatalog (REQ-68)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('labels OpenMousBot, never OMB, and ignores default catalog rows', () => {
    expect(remoteDisplayName({ id: 'omb', title: 'OpenMausBot' })).toBe(OPENMOUSBOT_LABEL)
    expect(remoteDisplayName({ id: 'omb', title: 'OMB' })).toBe(OPENMOUSBOT_LABEL)
    expect(remoteDisplayName({ id: 'hermes', title: 'Hermes' })).toBe('Hermes')
    const rail = parseRailRemotes({
      object: 'list',
      data: [
        { id: 'hermes', object: 'remote', title: 'Hermes', source: 'default' },
        { id: 'omb', object: 'remote', title: 'OMB', source: 'default' },
        {
          id: 'omb',
          title: 'OMB',
          configured: true,
          agents: [
            { id: 'cos', name: 'CoS', started_at: '2026-09-03T00:00:00Z' },
            { id: 'w1', name: 'Worker 1', started_at: '2026-09-03T00:00:01Z' },
          ],
        },
        {
          id: 'lab-swarm',
          kind: 'open-swarm',
          title: 'Lab swarm',
          configured: true,
          agents: [{ id: 'nested-cos', name: 'CoS' }],
        },
      ],
    })
    expect(rail.map((row) => row.id)).toEqual(['omb', 'lab-swarm'])
    expect(rail.map((row) => row.title)).not.toContain('Hermes')
    expect(rail.map((row) => row.title)).toContain(OPENMOUSBOT_LABEL)
    expect(JSON.stringify(rail)).not.toMatch(/\bOMB\b/)
  })

  it('does not pin unconfigured Hermes (catalog placeholder, issue #430)', () => {
    const rail = parseRailRemotes({
      object: 'list',
      data: [{ id: 'hermes', object: 'remote', title: 'Hermes', source: 'default' }],
    })
    expect(rail).toEqual([])
  })

  it('parses a configured-only list payload used by Settings / RemoteSelect', () => {
    const rail = parseRailRemotes({
      object: 'list',
      configured: [
        {
          id: 'omb',
          kind: 'omb',
          title: 'OpenMousBot',
          source: 'config',
        },
      ],
    })
    expect(rail.map((row) => row.id)).toEqual(['omb'])
    expect(rail[0]?.configured).toBe(true)
  })

  it('ignores blueprint-shaped GET payloads so a mixed mock cannot poison the rail', () => {
    expect(
      parseRailRemotes({
        object: 'list',
        data: [{ id: 'codey', object: 'blueprint', name: 'Codey' }],
      }),
    ).toEqual([])
  })

  it('fetchConfiguredRemotes is GET list only and empty on failure', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({}),
    })
    vi.stubGlobal('fetch', fetchMock)
    await expect(fetchConfiguredRemotes()).resolves.toEqual([])
    expect(fetchMock).toHaveBeenCalledWith('/remotes_catalog.json', {
      headers: { Accept: 'application/json' },
    })
    expect(fetchMock).toHaveBeenCalledWith('/v1/remotes/', { headers: { Accept: 'application/json' } })
    expect(fetchMock.mock.calls.map((call) => String(call[0])).join(' ')).not.toMatch(
      /health|operate/,
    )
  })
})
