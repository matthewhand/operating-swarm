import { describe, it, expect } from 'vitest'
import { assignUniqueLooks, allAvatarLooks, buildSearchHits } from '../agent-utils'
import type { Agent, ChatMessage, DelegationEvent } from '../../types/agent'

const agents: Agent[] = [
  {
    agent_id: 'coder',
    name: 'Coder',
    specialty: 'software development',
    color: '#f59e0b',
    icon: '💻',
    type: 'specialist',
    group: 'tools',
  },
  {
    agent_id: 'writer',
    name: 'Writer',
    specialty: 'content creation',
    color: '#10b981',
    icon: '✍️',
    type: 'specialist',
    group: 'specialists',
  },
]

const messages: ChatMessage[] = [
  {
    key: 'm1',
    role: 'user',
    text: 'write a fibonacci generator',
    timestamp: new Date(),
  },
  {
    key: 'm2',
    role: 'assistant',
    text: 'Here is the code',
    agent: 'Coder',
    agent_id: 'coder',
    timestamp: new Date(),
  },
]

const delegations: DelegationEvent[] = [
  {
    id: 'd1',
    from_agent: 'router',
    from_agent_name: 'Agent Router',
    to_agent: 'coder',
    to_agent_name: 'Coder',
    query: 'implement a queue',
    response: 'done',
    timestamp: 1,
  },
]

describe('buildSearchHits', () => {
  it('lists bots, messages, and delegations under All when query is empty', () => {
    const hits = buildSearchHits({
      agents,
      messages,
      delegations,
      query: '',
      scope: 'all',
    })
    const kinds = hits.map((h) => h.kind)
    expect(kinds).toContain('bot')
    expect(kinds).toContain('message')
    expect(kinds).toContain('delegation')
  })

  it('filters to bots only', () => {
    const hits = buildSearchHits({
      agents,
      messages,
      delegations,
      query: 'code',
      scope: 'bots',
    })
    expect(hits.every((h) => h.kind === 'bot')).toBe(true)
    expect(hits.some((h) => h.agentId === 'coder')).toBe(true)
    expect(hits.some((h) => h.agentId === 'writer')).toBe(false)
  })

  it('filters messages by text', () => {
    const hits = buildSearchHits({
      agents,
      messages,
      delegations,
      query: 'fibonacci',
      scope: 'messages',
    })
    expect(hits).toHaveLength(1)
    expect(hits[0].kind).toBe('message')
  })
})

describe('assignUniqueLooks', () => {
  it('gives each agent a unique pack+eyes pair when the roster fits the deck', () => {
    const ids = Array.from({ length: 40 }, (_, i) => `a${i}`)
    const { themes, eyes } = assignUniqueLooks(ids, {}, {}, { random: () => 0.3 })
    const pairs = ids.map((id) => `${themes[id]}:${eyes[id]}`)
    expect(new Set(pairs).size).toBe(40)
    expect(pairs.every((p) => p.includes(':'))).toBe(true)
  })

  it('keeps existing assignments and fills only newcomers', () => {
    const { themes, eyes } = assignUniqueLooks(
      ['coder', 'writer'],
      { coder: 'ghost' },
      { coder: 'googly' },
      { random: () => 0.2 },
    )
    expect(themes.coder).toBe('ghost')
    expect(eyes.coder).toBe('googly')
    expect(`${themes.writer}:${eyes.writer}`).not.toBe('ghost:googly')
  })

  it('has 60 unique looks in the deck', () => {
    expect(allAvatarLooks()).toHaveLength(10 * 6)
  })

  // #128: Apply to all agents must draw from the installed set only.
  it('builds the deck from the installed themes when given a subset', () => {
    expect(allAvatarLooks(['blobs', 'bee'])).toHaveLength(2 * 6)
    expect(allAvatarLooks(['blobs', 'bee']).every((l) => ['blobs', 'bee'].includes(l.theme))).toBe(
      true,
    )

    const ids = Array.from({ length: 12 }, (_, i) => `a${i}`)
    const { themes } = assignUniqueLooks(ids, {}, {}, { themes: ['blobs', 'bee'] })
    expect(ids.every((id) => ['blobs', 'bee'].includes(themes[id]))).toBe(true)
  })

  it('falls back to the full deck when the installed set is empty or unknown', () => {
    expect(allAvatarLooks([])).toHaveLength(60)
    expect(allAvatarLooks(['not-a-theme' as never])).toHaveLength(60)
  })
})
