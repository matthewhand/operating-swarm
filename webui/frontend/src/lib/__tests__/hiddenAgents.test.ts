import { afterEach, describe, expect, it } from 'vitest'
import {
  DEFAULT_HIDDEN_AGENT_IDS,
  HIDDEN_AGENTS_STORAGE_KEY,
  LEGACY_HIDDEN_AGENTS_STORAGE_KEY,
  agentMarkColor,
  canHideAgent,
  defaultHiddenAgentIds,
  hideAgentId,
  hideAllAgentIds,
  loadHiddenAgentIds,
  loadOrSeedHiddenAgentIds,
  migrateLegacyHiddenAgentIds,
  reconcileHiddenAgentIds,
  saveHiddenAgentIds,
  unhideAgentId,
  unhideAllAgentIds,
} from '../hiddenAgents'

describe('hiddenAgents persistence', () => {
  afterEach(() => {
    localStorage.removeItem(HIDDEN_AGENTS_STORAGE_KEY)
    localStorage.removeItem(LEGACY_HIDDEN_AGENTS_STORAGE_KEY)
  })

  it('reads empty when nothing is stored (seed is opt-in via loadOrSeed)', () => {
    expect(loadHiddenAgentIds()).toEqual([])
  })

  it('seeds gate and skeptic catalog ids on first load', () => {
    const catalog = [
      { id: 'support', name: 'Support' },
      { id: 'tool_gate', name: 'Gate' },
      { id: 'skeptic', name: 'Skeptic' },
      { id: 'codey', name: 'Codey' },
    ]
    expect(defaultHiddenAgentIds(catalog)).toEqual(['tool_gate', 'skeptic'])
    expect(loadOrSeedHiddenAgentIds(catalog)).toEqual(['tool_gate', 'skeptic'])
    expect(JSON.parse(localStorage.getItem(HIDDEN_AGENTS_STORAGE_KEY) || '[]')).toEqual([
      'tool_gate',
      'skeptic',
    ])
    expect(loadOrSeedHiddenAgentIds(catalog)).toEqual(['tool_gate', 'skeptic'])
  })

  it('falls back to shipped aliases when the catalog has no gate/skeptic yet', () => {
    expect(loadOrSeedHiddenAgentIds([{ id: 'codey', name: 'Codey' }])).toEqual([
      ...DEFAULT_HIDDEN_AGENT_IDS,
    ])
  })

  it('does not re-seed after the user unhides (empty stored list)', () => {
    saveHiddenAgentIds([])
    expect(loadOrSeedHiddenAgentIds([{ id: 'gate', name: 'Gate' }])).toEqual([])
    expect(localStorage.getItem(HIDDEN_AGENTS_STORAGE_KEY)).toBe('[]')
  })

  it('does not overwrite an existing customized hidden list', () => {
    saveHiddenAgentIds(['codey'])
    expect(loadOrSeedHiddenAgentIds([{ id: 'gate', name: 'Gate' }])).toEqual(['codey'])
  })

  it('hides an agent and persists across a reload-style read', () => {
    const next = hideAgentId('codey', [])
    expect(next).toEqual(['codey'])
    expect(JSON.parse(localStorage.getItem(HIDDEN_AGENTS_STORAGE_KEY) || '[]')).toEqual(['codey'])
    expect(loadHiddenAgentIds()).toEqual(['codey'])
  })

  it('hides all ids and unhides a single agent', () => {
    const afterAll = hideAllAgentIds(['codey', 'stewie'])
    expect(afterAll).toEqual(['codey', 'stewie'])
    expect(loadHiddenAgentIds()).toEqual(['codey', 'stewie'])
    const afterUnhide = unhideAgentId('codey', afterAll)
    expect(afterUnhide).toEqual(['stewie'])
    expect(unhideAllAgentIds()).toEqual([])
    expect(loadHiddenAgentIds()).toEqual([])
  })

  it('ignores corrupt storage and empty ids', () => {
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, '{not-json')
    expect(loadHiddenAgentIds()).toEqual([])
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify([1, '', 'ok']))
    expect(loadHiddenAgentIds()).toEqual(['ok'])
    expect(hideAgentId('', ['ok'])).toEqual(['ok'])
  })

  it('assigns a stable small accent per agent id', () => {
    expect(agentMarkColor('codey')).toBe(agentMarkColor('codey'))
    expect(agentMarkColor('codey')).not.toBe(agentMarkColor('stewie'))
  })

  it('does not exempt role agents (support, gate, skeptic) from hide', () => {
    for (const id of ['support', 'gate', 'skeptic', 'codey']) {
      expect(canHideAgent(id)).toBe(true)
      expect(hideAgentId(id, [])).toEqual([id])
    }
  })

  describe('#548 legacy agent_hidden_ids migration', () => {
    it('adopts the legacy list when the canonical key is absent — no seeding', () => {
      localStorage.setItem(LEGACY_HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify(['codey']))

      // The rail's first load is where the seed used to overwrite the user.
      const seeded = loadOrSeedHiddenAgentIds([{ id: 'gate' }, { id: 'skeptic' }])

      expect(seeded).toEqual(['codey'])
      expect(loadHiddenAgentIds()).toEqual(['codey'])
      // Nothing was seeded over the top, and the legacy key is retired.
      expect(localStorage.getItem(LEGACY_HIDDEN_AGENTS_STORAGE_KEY)).toBeNull()
      expect(DEFAULT_HIDDEN_AGENT_IDS.every((id) => !seeded.includes(id))).toBe(true)
    })

    it('lets the canonical list win when both keys are set — dropped, not merged', () => {
      localStorage.setItem(LEGACY_HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify(['codey']))
      saveHiddenAgentIds(['stewie'])

      const migrated = migrateLegacyHiddenAgentIds()

      expect(migrated).toEqual(['stewie'])
      // 'codey' must NOT reappear — merging would re-hide what the user unhid.
      expect(loadHiddenAgentIds()).toEqual(['stewie'])
      expect(localStorage.getItem(LEGACY_HIDDEN_AGENTS_STORAGE_KEY)).toBeNull()
    })

    it('is a no-op — returning null — when there is no legacy key', () => {
      expect(migrateLegacyHiddenAgentIds()).toBeNull()
      // and the canonical seed path still runs
      const seeded = loadOrSeedHiddenAgentIds([{ id: 'gate' }])
      expect(seeded.length).toBeGreaterThan(0)
    })

    it('migrates an empty legacy list rather than treating it as absent', () => {
      localStorage.setItem(LEGACY_HIDDEN_AGENTS_STORAGE_KEY, '[]')
      expect(migrateLegacyHiddenAgentIds()).toEqual([])
      expect(loadOrSeedHiddenAgentIds([{ id: 'gate' }, { id: 'skeptic' }])).toEqual([])
    })
  })

  describe('reconcileHiddenAgentIds (#170)', () => {
    it('keeps hide ids that match a live rail row', () => {
      const live = ['codey', 'stewie', 'team:research-squad', 'remote:hermes']
      const hidden = ['codey', 'team:research-squad', 'remote:hermes']
      expect(reconcileHiddenAgentIds(hidden, live)).toEqual([
        'codey',
        'team:research-squad',
        'remote:hermes',
      ])
    })

    it('drops stale team hide ids whose roster no longer exists (#170)', () => {
      const live = ['codey', 'team:research-squad']
      const hidden = ['team:demo-team', 'gate', 'team:old-harness', 'codey']
      // gate is stale here too (not a live row) — only live ids survive.
      expect(reconcileHiddenAgentIds(hidden, live)).toEqual(['codey'])
    })

    it('keeps pinned ids hideable even when their row is not listed', () => {
      const hidden = ['codey', 'team:demo-harness-kinds']
      const live = ['codey']
      const pinned = ['team:demo-harness-kinds']
      expect(reconcileHiddenAgentIds(hidden, live, pinned)).toEqual([
        'codey',
        'team:demo-harness-kinds',
      ])
    })

    it('is idempotent and never invents ids', () => {
      const live = ['codey']
      const once = reconcileHiddenAgentIds(['gate', 'team:gone'], live)
      expect(reconcileHiddenAgentIds(once, live)).toEqual(once)
      expect(once).not.toContain('team:gone')
    })
  })
})
