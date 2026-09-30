import { describe, expect, it } from 'vitest'
import {
  ADD_ROUTINE_LABEL,
  SUPPORT_INTERACTIVE_FIXTURE,
  parseSupportNlRoutineFence,
} from '../supportNlRoutine'

const SAMPLE = `Drafted routine **Daily standup** for \`codey\`.

**${ADD_ROUTINE_LABEL}** saves it with the existing routines API.

\`\`\`swarm-nl-routine
{
  "id": "",
  "kind": "routine",
  "title": "Daily standup",
  "agentId": "codey",
  "instruction": "posts notes",
  "trigger": {"kind": "cron", "expression": "0 9 * * *"},
  "triggerLabel": "Daily at 09:00",
  "persisted": false,
  "usable": false,
  "chatHref": "/chat?blueprint=codey",
  "fixture": "${SUPPORT_INTERACTIVE_FIXTURE}"
}
\`\`\`
`

describe('supportNlRoutine (#1373)', () => {
  it('extracts the card and strips the fence from prose', () => {
    const { prose, card } = parseSupportNlRoutineFence(SAMPLE)
    expect(card?.title).toBe('Daily standup')
    expect(card?.agentId).toBe('codey')
    expect(card?.persisted).toBe(false)
    expect(card?.trigger.kind).toBe('cron')
    expect(prose).toContain(ADD_ROUTINE_LABEL)
    expect(prose).not.toContain('swarm-nl-routine')
    expect(prose).not.toContain('0 9 * * *')
  })

  it('returns no card without a fence', () => {
    const { card } = parseSupportNlRoutineFence('Create a routine later.')
    expect(card).toBeNull()
  })
})
