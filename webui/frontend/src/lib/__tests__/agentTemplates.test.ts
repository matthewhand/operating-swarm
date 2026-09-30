import { describe, expect, it, vi } from 'vitest'
import {
  SHIPPED_STOREFRONT_BEE,
  SHIPPED_SWARM_ENGINEER,
  appliedSummary,
  catalogItemFromPack,
  importChecklist,
  downloadTemplateJson,
  filterTemplateItems,
  installTargetFromCurrentAgent,
  isAgentTemplatePack,
  isGrokTemplate,
  parseTemplateJson,
  shippedTemplateCatalog,
  templateDisplayName,
  templateGettingStarted,
} from '../agentTemplates'

const GROK = {
  kind: 'grok_bot_template',
  name: 'Storefront Bee',
  description: 'Short storefront blurb for the rail and pack card.',
  role: 'support',
  memories: [{ kind: 'profile', title: 'Voice', body: 'Keep it short.' }],
  skills: [{ name: 'welcome-tour' }],
  gettingStarted: { skill: 'welcome-tour' },
}

describe('#1399 agentTemplates catalog helpers', () => {
  it('ships native Storefront Bee and Swarm Engineer packs', () => {
    const cards = shippedTemplateCatalog()
    expect(cards.map((card) => card.id)).toEqual(['shipped-storefront-bee', 'shipped-swarm-engineer'])
    expect(cards.every((card) => card.sourceLabel === 'Native')).toBe(true)
    expect(cards[0].skillNames).toEqual(['welcome-tour'])
    expect(cards[1].gettingStarted).toBe('implement-issue')
    const blob = JSON.stringify({ bee: SHIPPED_STOREFRONT_BEE, engineer: SHIPPED_SWARM_ENGINEER })
    expect(blob).not.toMatch(/sk-|api_key|password|bearer /i)
    expect(importChecklist({
      agent_id: 'swarm-engineer',
      template: SHIPPED_SWARM_ENGINEER,
      fill_ins_remaining: [{ key: 'owner_repo', label: 'GitHub owner/repo' }],
      plugins_missing: ['web_search'],
    })).toEqual({
      agentId: 'swarm-engineer',
      fillIns: [{ key: 'owner_repo', label: 'GitHub owner/repo' }],
      connect: ['web_search'],
      gettingStarted: 'implement-issue',
    })
  })

  it('detects pack vs Grok shapes and names them', () => {
    expect(isAgentTemplatePack(SHIPPED_STOREFRONT_BEE)).toBe(true)
    expect(isGrokTemplate(SHIPPED_STOREFRONT_BEE)).toBe(false)
    expect(isGrokTemplate(GROK)).toBe(true)
    expect(templateDisplayName(GROK)).toBe('Storefront Bee')
    expect(templateGettingStarted(GROK)).toBe('welcome-tour')
  })

  it('filters cards by name, role, and skill', () => {
    const extra = catalogItemFromPack(
      { ...SHIPPED_STOREFRONT_BEE, profile: { ...SHIPPED_STOREFRONT_BEE.profile, display_name: 'Night Watch' } },
      { id: 'night', source: 'file', sourceLabel: 'Pack file' },
    )
    const rows = [...shippedTemplateCatalog(), extra]
    expect(filterTemplateItems(rows, 'bee').map((row) => row.id)).toEqual(['shipped-storefront-bee'])
    expect(filterTemplateItems(rows, 'welcome-tour')).toHaveLength(2)
    expect(filterTemplateItems(rows, 'night')).toEqual([extra])
  })

  it('refuses scoped conversation ids as install targets', () => {
    expect(installTargetFromCurrentAgent({ id: 'codey', kind: 'api' })).toBe('codey')
    expect(installTargetFromCurrentAgent({ id: 'team:lab', kind: 'api' })).toBe('')
    expect(installTargetFromCurrentAgent({ id: 'remote:omb', kind: 'remote' })).toBe('')
    expect(installTargetFromCurrentAgent(null)).toBe('')
  })

  it('parses pack JSON and rejects junk', () => {
    expect(parseTemplateJson(JSON.stringify(SHIPPED_STOREFRONT_BEE)).kind).toBe('agent_template')
    expect(() => parseTemplateJson('{')).toThrow(/not valid JSON/i)
    expect(() => parseTemplateJson('[]')).toThrow(/JSON object/i)
  })

  it('summarizes applied import counts', () => {
    expect(appliedSummary({ memories: 2, skills: 1, routines: 0, plugins: 0 })).toBe(
      'Installed profile, 2 memories, 1 skill, 0 routines, 0 plugins.',
    )
    expect(appliedSummary({ memories: 1, skills: 2, routines: 1, plugins: 0 })).toBe(
      'Installed profile, 1 memory, 2 skills, 1 routine, 0 plugins.',
    )
  })

  it('downloads JSON without embedding secrets in the helper', () => {
    const click = vi.fn()
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:template'),
      revokeObjectURL: vi.fn(),
    })
    const created: HTMLAnchorElement[] = []
    const original = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = original(tag)
      if (tag === 'a') {
        el.click = click
        created.push(el as HTMLAnchorElement)
      }
      return el
    })
    downloadTemplateJson('bee.json', SHIPPED_STOREFRONT_BEE)
    expect(click).toHaveBeenCalled()
    expect(created[0]?.download).toBe('bee.json')
    vi.restoreAllMocks()
  })
})
