import { describe, it, expect, beforeEach } from 'vitest'
import {
  buildSlashCatalog,
  filterSlashItems,
  groupSlashItems,
  getRecentSlashIds,
  recordRecentSlashId,
  clearRecentSlashIds,
  DEFAULT_ACTIONS,
  DEFAULT_SKILLS,

} from '../slashMenu'

describe('slashMenu helpers', () => {
  beforeEach(() => {
    clearRecentSlashIds()
  })

  it('buildSlashCatalog combines default actions, default skills, and dynamic skills', () => {
    const catalog = buildSlashCatalog([
      { name: 'custom-skill', description: 'Custom dynamic skill' },
    ])
    expect(catalog.length).toBe(DEFAULT_ACTIONS.length + DEFAULT_SKILLS.length + 1)
    const custom = catalog.find((item) => item.id === 'custom-skill')
    expect(custom).toBeDefined()
    expect(custom?.kind).toBe('skill')
    expect(custom?.title).toBe('Custom Skill')
    expect(custom?.command).toBe('/skill custom-skill')
  })

  it('records recency and maintains most recent at front', () => {
    expect(getRecentSlashIds()).toEqual([])
    recordRecentSlashId('compact')
    recordRecentSlashId('conventional-commit')
    expect(getRecentSlashIds()).toEqual(['conventional-commit', 'compact'])

    // Re-recording moves to front
    recordRecentSlashId('compact')
    expect(getRecentSlashIds()).toEqual(['compact', 'conventional-commit'])
  })

  it('empty query puts recent items first, then alphabetical within section', () => {
    const catalog = buildSlashCatalog()
    const recentIds = ['conventional-commit', 'clear']

    const result = filterSlashItems(catalog, '', recentIds)
    // First two items should be recents in order
    expect(result[0].id).toBe('conventional-commit')
    expect(result[1].id).toBe('clear')

    // Remaining items should be actions (alphabetical), then skills (alphabetical)
    const nonRecents = result.slice(2)
    const nonRecentActions = nonRecents.filter((x) => x.kind === 'action')
    const nonRecentSkills = nonRecents.filter((x) => x.kind === 'skill')

    expect(nonRecentActions.map((a) => a.title)).toEqual([
      'Approval',
      'Compact',
      'Help',
      'History',
      'Model',
    ])
    expect(nonRecentSkills.map((s) => s.title)).toEqual([
      'Counting Lines',
      'Reviewing Code',
      'Support Session Ownership',
      'Writing Changelog',
    ])
  })

  it('filters by query and ranks command/name starts-with higher', () => {
    const catalog = buildSlashCatalog()
    // query "co" matches "compact", "conventional-commit", "counting-lines"
    const result = filterSlashItems(catalog, '/co', [])
    const ids = result.map((r) => r.id)
    expect(ids).toContain('compact')
    expect(ids).toContain('conventional-commit')
    expect(ids).toContain('counting-lines')
  })

  it('filters by description substring', () => {
    const catalog = buildSlashCatalog()
    // "backlog" appears in compact description
    const result = filterSlashItems(catalog, 'backlog', [])
    expect(result.length).toBe(1)
    expect(result[0].id).toBe('compact')
  })

  it('groupSlashItems partitions into Recent, Actions, Skills when query empty', () => {
    const catalog = buildSlashCatalog()
    const groups = groupSlashItems(catalog, '', ['compact'])
    expect(groups.length).toBe(3)
    expect(groups[0].label).toBe('Recent')
    expect(groups[0].items.map((i) => i.id)).toEqual(['compact'])
    expect(groups[1].label).toBe('Actions')
    expect(groups[2].label).toBe('Skills')
  })

  it('groupSlashItems partitions into Actions and Skills when query non-empty', () => {
    const catalog = buildSlashCatalog()
    const filtered = filterSlashItems(catalog, 'co', [])
    const groups = groupSlashItems(filtered, 'co', [])
    expect(groups.map((g) => g.label)).toEqual(['Actions', 'Skills'])
  })
})
