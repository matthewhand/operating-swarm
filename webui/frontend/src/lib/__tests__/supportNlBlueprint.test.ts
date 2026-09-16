import { describe, expect, it } from 'vitest'
import {
  SUPPORT_NL_FIXTURE,
  parseSupportNlBlueprintFence,
  supportNlCreateRequiresUserPython,
} from '../supportNlBlueprint'

const SAMPLE = `Drafted **BA → Engineer → Tester**. You did not write Python.

\`\`\`swarm-nl-blueprint
{
  "id": "ba_eng_tester",
  "title": "BA → Engineer → Tester",
  "usable": false,
  "persisted": false,
  "chatHref": "/chat?blueprint=ba_eng_tester",
  "graphLabel": "BA → Engineer → Tester",
  "edges": [["ba", "engineer"], ["engineer", "tester"]],
  "fixture": "${SUPPORT_NL_FIXTURE}",
  "userWrotePython": false,
  "code": "from swarm.core.kind_bases import ApiKindBase\\n"
}
\`\`\`
`

describe('supportNlBlueprint (REQ-158)', () => {
  it('extracts the card and strips the fence from prose', () => {
    const { prose, card } = parseSupportNlBlueprintFence(SAMPLE)
    expect(card?.id).toBe('ba_eng_tester')
    expect(card?.usable).toBe(false)
    expect(card?.persisted).toBe(false)
    expect(card?.userWrotePython).toBe(false)
    expect(card?.edges).toEqual([
      ['ba', 'engineer'],
      ['engineer', 'tester'],
    ])
    expect(prose).toContain('You did not write Python')
    expect(prose).not.toContain('swarm-nl-blueprint')
    expect(prose).not.toContain('ApiKindBase')
    expect(supportNlCreateRequiresUserPython(card)).toBe(false)
  })

  it('returns no card when the user would have to write Python', () => {
    const { card } = parseSupportNlBlueprintFence('Please paste a class yourself.')
    expect(card).toBeNull()
    expect(supportNlCreateRequiresUserPython(card)).toBe(false)
  })
})
