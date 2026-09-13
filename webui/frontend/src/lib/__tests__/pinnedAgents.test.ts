import { afterEach, describe, expect, it } from 'vitest'
import {
  DEFAULT_PINNED_SUPPORT,
  PINNED_AGENTS_STORAGE_KEY,
  excludePinnedFromList,
  loadOrSeedPinnedAgents,
  loadPinnedAgents,
  movePinnedAgent,
  pinAgent,
  unpinAgent,
  writeAgentDragPayload,
} from '../pinnedAgents'

describe('pinnedAgents persistence', () => {
  afterEach(() => {
    localStorage.removeItem(PINNED_AGENTS_STORAGE_KEY)
  })

  it('seeds Support on first load when prefs are missing, but not when empty []', () => {
    expect(loadOrSeedPinnedAgents()).toEqual([DEFAULT_PINNED_SUPPORT])
    expect(loadPinnedAgents()).toEqual([DEFAULT_PINNED_SUPPORT])
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
    expect(loadOrSeedPinnedAgents()).toEqual([])
  })

  it('starts empty and pins without duplicates', () => {
    expect(loadPinnedAgents()).toEqual([])
    const next = pinAgent({ id: 'codey', name: 'Codey' }, [])
    expect(next).toEqual([{ id: 'codey', name: 'Codey' }])
    expect(pinAgent({ id: 'codey', name: 'Codey' }, next)).toEqual(next)
    expect(loadPinnedAgents()).toEqual([{ id: 'codey', name: 'Codey' }])
  })

  it('unpins a single favourite', () => {
    const pinned = pinAgent({ id: 'stewie', name: 'Stewie' }, [{ id: 'codey', name: 'Codey' }])
    expect(unpinAgent('codey', pinned)).toEqual([{ id: 'stewie', name: 'Stewie' }])
    expect(loadPinnedAgents()).toEqual([{ id: 'stewie', name: 'Stewie' }])
  })

  it('reorders favourites and persists the new order', () => {
    const pinned = pinAgent({ id: 'stewie', name: 'Stewie' }, [{ id: 'codey', name: 'Codey' }])
    const next = movePinnedAgent('stewie', 'codey', pinned)
    expect(next.map((pin) => pin.id)).toEqual(['stewie', 'codey'])
    expect(loadPinnedAgents().map((pin) => pin.id)).toEqual(['stewie', 'codey'])
    expect(movePinnedAgent('stewie', 'stewie', next)).toEqual(next)
    expect(movePinnedAgent('missing', 'codey', next)).toEqual(next)
  })

  it('drops favourited ids from the rail list (move, not copy)', () => {
    const rows = [{ id: 'codey' }, { id: 'stewie' }, { id: 'support' }]
    const pins = pinAgent({ id: 'codey', name: 'Codey' }, [])
    expect(excludePinnedFromList(rows, pins).map((row) => row.id)).toEqual(['stewie', 'support'])
    expect(excludePinnedFromList(rows, unpinAgent('codey', pins)).map((row) => row.id)).toEqual([
      'codey',
      'stewie',
      'support',
    ])
  })

  it('clears URL and URI drag data to prevent browser split view popup (#702)', () => {
    const data: Record<string, string> = {
      'text/uri-list': 'http://198.51.100.30:8001/chat?blueprint=codey',
      'URL': 'http://198.51.100.30:8001/chat?blueprint=codey',
      'text/html': '<a href="http://198.51.100.30:8001/chat?blueprint=codey">Codey</a>',
    }
    const mockDataTransfer = {
      setData: (key: string, val: string) => {
        data[key] = val
      },
      getData: (key: string) => data[key] || '',
      clearData: (key?: string) => {
        if (!key) {
          for (const k of Object.keys(data)) delete data[k]
        } else {
          delete data[key]
        }
      },
      effectAllowed: 'none',
    } as unknown as DataTransfer

    writeAgentDragPayload(mockDataTransfer, { id: 'codey', name: 'Codey' })
    expect(data['text/uri-list']).toBeUndefined()
    expect(data['URL']).toBeUndefined()
    expect(data['text/html']).toBeUndefined()
    expect(data['text/plain']).toBe('codey')
  })
})

