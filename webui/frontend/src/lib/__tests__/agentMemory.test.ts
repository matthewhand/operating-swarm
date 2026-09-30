import { describe, expect, it } from 'vitest'
import {
  filterMemories,
  groupMemoriesByTier,
  memoriesPath,
  memoryPackPath,
  memoryPath,
  parseMemories,
  previewMemoryExport,
  skipReasonFor,
  type AgentMemory,
} from '../agentMemory'

function row(
  partial: Partial<AgentMemory> & Pick<AgentMemory, 'id' | 'kind'>,
): AgentMemory {
  return {
    object: 'agent_memory',
    agent_id: 'codey',
    tier: partial.kind === 'episode' || partial.kind === 'note' ? 'local' : 'pack',
    title: '',
    body: '',
    created_at: '2026-09-27T00:00:00.000Z',
    ...partial,
  }
}

const FIXTURES: AgentMemory[] = [
  row({ id: 'p1', kind: 'profile', title: 'Voice', body: 'Prefers short answers.' }),
  row({ id: 'l1', kind: 'log', title: 'Weekly review', body: 'Shipped the rail polish.' }),
  row({ id: 'e1', kind: 'episode', title: 'Tuesday chat', body: 'Private Tuesday chat.' }),
  row({ id: 'n1', kind: 'note', title: 'Scratch', body: 'Do not pack this.' }),
]

describe('#1391 agent memory list/filter', () => {
  it('parses a list payload and ignores unknown rows', () => {
    const parsed = parseMemories(
      {
        object: 'agent_memory_list',
        agent_id: 'codey',
        memories: [
          ...FIXTURES,
          { kind: 'profile', title: 'Missing id' },
          { id: 'x', kind: 'unknown', body: 'Nope' },
        ],
      },
      'codey',
    )
    expect(parsed.map((item) => item.id)).toEqual(['p1', 'l1', 'e1', 'n1'])
    expect(parsed.every((item) => item.agent_id === 'codey')).toBe(true)
  })

  it('filters by tier and by kind', () => {
    expect(filterMemories(FIXTURES, 'all')).toHaveLength(4)
    expect(filterMemories(FIXTURES, 'pack').map((item) => item.kind)).toEqual(['profile', 'log'])
    expect(filterMemories(FIXTURES, 'local').map((item) => item.kind)).toEqual(['episode', 'note'])
    expect(filterMemories(FIXTURES, 'log').map((item) => item.id)).toEqual(['l1'])
  })

  it('groups list rows by pack vs local tier', () => {
    const grouped = groupMemoriesByTier(FIXTURES)
    expect(grouped.pack.map((item) => item.id)).toEqual(['p1', 'l1'])
    expect(grouped.local.map((item) => item.id)).toEqual(['e1', 'n1'])
  })

  it('keeps a row in one tier when the declared tier disagrees with kind', () => {
    const mismatched = [
      row({ id: 'p1', kind: 'profile', tier: 'local', title: 'Voice', body: 'Short answers.' }),
    ]
    const grouped = groupMemoriesByTier(mismatched)
    expect(grouped.pack.map((item) => item.id)).toEqual(['p1'])
    expect(grouped.local).toEqual([])
    expect(filterMemories(mismatched, 'pack')).toHaveLength(1)
    expect(filterMemories(mismatched, 'local')).toHaveLength(0)
    const parsed = parseMemories(
      [{ id: 'p1', kind: 'profile', tier: 'local', title: 'Voice', body: 'Short answers.' }],
      'codey',
    )
    expect(parsed[0]?.tier).toBe('pack')
  })

  it('builds the #1390 memory URLs', () => {
    expect(memoriesPath('codey')).toBe('/v1/agents/codey/memories/')
    expect(memoryPath('codey', 'p1')).toBe('/v1/agents/codey/memories/p1/')
    expect(memoryPackPath('codey')).toBe('/v1/agents/codey/memories/pack/')
  })
})

describe('#1391 memory export preview', () => {
  it('includes pack conventions and skips episode/note with reasons', () => {
    const preview = previewMemoryExport(FIXTURES)
    expect(preview.includedCount).toBe(2)
    expect(preview.excludedCount).toBe(2)
    expect(preview.included.map((item) => item.kind)).toEqual(['profile', 'log'])
    expect(preview.excluded.map((item) => item.reason)).toEqual([
      'episode_skipped',
      'note_skipped',
    ])
    expect(skipReasonFor('episode')).toBe('episode_skipped')
    expect(skipReasonFor('note')).toBe('note_skipped')
    expect(skipReasonFor('profile')).toBeNull()
  })

  it('keeps fixture prose free of credential-shaped strings', () => {
    const blob = FIXTURES.map((item) => `${item.title} ${item.body}`).join(' ')
    expect(blob).not.toMatch(/sk-|api[_-]?key|password|secret|token=/i)
  })
})
