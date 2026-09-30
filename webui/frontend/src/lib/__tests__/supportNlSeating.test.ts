import { describe, expect, it } from 'vitest'
import {
  CREATE_GROUP_LABEL,
  SEAT_ON_TEAM_LABEL,
  seatingCtaLabel,
  parseSupportNlSeatingFence,
} from '../supportNlSeating'

const SAMPLE = `Drafted seating **office**: Ada.

**${SEAT_ON_TEAM_LABEL}** writes the existing team-roster store.

\`\`\`swarm-nl-seating
{
  "id": "office",
  "kind": "seating",
  "title": "office",
  "mode": "seat",
  "members": [{"id": "ada", "name": "Ada", "kind": "api", "role": "default"}],
  "memberLabel": "Ada",
  "persisted": false,
  "usable": false,
  "chatHref": "/chat?team=office"
}
\`\`\`
`

describe('supportNlSeating (#1373)', () => {
  it('extracts the card and strips the fence from prose', () => {
    const { prose, card } = parseSupportNlSeatingFence(SAMPLE)
    expect(card?.id).toBe('office')
    expect(card?.members).toEqual([
      { id: 'ada', name: 'Ada', kind: 'api', role: 'default', source: undefined },
    ])
    expect(card?.persisted).toBe(false)
    expect(seatingCtaLabel(card!)).toBe(SEAT_ON_TEAM_LABEL)
    expect(prose).toContain(SEAT_ON_TEAM_LABEL)
    expect(prose).not.toContain('swarm-nl-seating')
  })

  it('labels create-group cards', () => {
    const { card } = parseSupportNlSeatingFence(`\`\`\`swarm-nl-seating
{"id":"desk","title":"Desk","mode":"create_group","members":[],"memberLabel":"Ada, Pat","persisted":false}
\`\`\``)
    expect(card?.mode).toBe('create_group')
    expect(seatingCtaLabel(card!)).toBe(CREATE_GROUP_LABEL)
  })
})
