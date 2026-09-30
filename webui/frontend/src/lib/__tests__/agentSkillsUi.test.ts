import { describe, expect, it } from 'vitest'
import {
  WHEN_TO_USE_LABEL,
  canExportAgentPack,
  exportBlockedReason,
  gettingStartedFlowFromList,
  gettingStartedInSelection,
  parsePackJson,
  pickerOptionsForSelection,
  skillWhenToUse,
} from '../agentSkillsUi'

describe('agentSkillsUi (#1393)', () => {
  it('treats description as when-to-use', () => {
    expect(WHEN_TO_USE_LABEL).toBe('When to use')
    expect(skillWhenToUse({ description: 'Walk the first conversation.' })).toBe(
      'Walk the first conversation.',
    )
    expect(skillWhenToUse({ description: '  ' })).toBe('')
  })

  it('requires gettingStarted to name a selected skill', () => {
    expect(gettingStartedInSelection(['welcome-tour', 'review-notes'], 'welcome-tour')).toBe(true)
    expect(gettingStartedInSelection(['review-notes'], 'welcome-tour')).toBe(false)
    expect(gettingStartedInSelection(['welcome-tour'], { skill: 'welcome-tour' })).toBe(true)
    expect(gettingStartedInSelection([], 'welcome-tour')).toBe(false)
    expect(canExportAgentPack(['welcome-tour'], 'welcome-tour')).toBe(true)
    expect(canExportAgentPack(['welcome-tour', 'review-notes'], 'not-packed')).toBe(false)
    expect(canExportAgentPack([], 'welcome-tour')).toBe(false)
    expect(exportBlockedReason(['welcome-tour'], 'review-notes')).toMatch(/selected skill/)
    expect(exportBlockedReason([], 'welcome-tour')).toMatch(/at least one skill/)
    expect(exportBlockedReason(['welcome-tour'], '')).toMatch(/getting-started/)
    expect(pickerOptionsForSelection(['Review-Notes', 'welcome-tour'])).toEqual([
      'review-notes',
      'welcome-tour',
    ])
  })

  it('surfaces first-run getting-started from an imported list payload', () => {
    expect(
      gettingStartedFlowFromList({
        object: 'agent_skill_list',
        first_run_pending: true,
        gettingStarted: { skill: 'welcome-tour' },
        skills: [
          {
            name: 'welcome-tour',
            description: 'Walk the first conversation.',
            instructions: 'Say hi.',
          },
        ],
      }),
    ).toEqual({
      skill: 'welcome-tour',
      whenToUse: 'Walk the first conversation.',
      chip: 'Walk the first conversation.',
    })
    expect(
      gettingStartedFlowFromList({
        object: 'list',
        first_run_pending: true,
        gettingStarted: { skill: 'welcome-tour' },
        skills: [],
      }),
    ).toBeNull()
    expect(
      gettingStartedFlowFromList({
        object: 'agent_skill_list',
        first_run_pending: false,
        gettingStarted: { skill: 'welcome-tour' },
        skills: [{ name: 'welcome-tour', description: 'Hi', instructions: 'Hi' }],
      }),
    ).toBeNull()
  })

  it('parses pack JSON and unwraps a pack wrapper', () => {
    const pack = {
      kind: 'swarm-agent-pack',
      skills: [{ name: 'welcome-tour', description: 'Hi', instructions: 'Say hi.' }],
      gettingStarted: { skill: 'welcome-tour' },
    }
    expect(parsePackJson(JSON.stringify(pack))).toEqual(pack)
    expect(parsePackJson(JSON.stringify({ pack }))).toEqual(pack)
    expect(() => parsePackJson('{')).toThrow(/valid JSON/)
    expect(() => parsePackJson('   ')).toThrow(/Paste or drop/)
  })
})
