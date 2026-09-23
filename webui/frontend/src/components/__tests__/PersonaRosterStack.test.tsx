import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import PersonaRoster from '../PersonaRoster'
import type { DeclaredTeamRoster } from '../../lib/declaredRoster'

function roster(count: number, names: string[]): DeclaredTeamRoster {
  return {
    blueprintId: 'squad',
    generic: false,
    parsed: true,
    count,
    personas: names.map((name) => ({ name })),
  }
}

/**
 * #438 supersedes the old `#57` / REQ-891 plan for the sidepane. That plan fanned
 * 1–3 declared faces and collapsed 4+ to two faces plus a `+N`: at rail size the
 * faces were overlapping slivers that were not individually readable, and the
 * plan disagreed with the member-row rule beside it. The contract is now **one**
 * face — the chat target — plus a `+N` for the rest, on every roster size.
 *
 * The assertions below were rewritten rather than deleted, so the reversal is
 * visible in the diff instead of looking like coverage that quietly went away.
 */
describe('#438: declared PersonaRoster shows one face plus a remainder', () => {
  it('collapses a roster of 4 to one face and +3', () => {
    render(
      <PersonaRoster
        roster={roster(4, ['Alpha', 'Bravo', 'Charlie', 'Delta'])}
        groupId="squad"
      />,
    )
    const el = screen.getByTestId('declared-roster')
    expect(el).toHaveAttribute('data-stack-count', '1')
    expect(el).toHaveAttribute('data-remainder', '3')
    expect(el.querySelectorAll('[data-testid="os-stacked-avatar"]')).toHaveLength(0)
    expect(el.querySelector('[data-testid="declared-roster-face"]')).not.toBeNull()
    expect(screen.getByTestId('team-remainder')).toHaveTextContent('+3')
  })

  it('collapses a roster of 5 to one face and +4', () => {
    render(
      <PersonaRoster
        roster={roster(5, ['Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo'])}
        groupId="squad"
      />,
    )
    const el = screen.getByTestId('declared-roster')
    expect(el).toHaveAttribute('data-stack-count', '1')
    expect(el).toHaveAttribute('data-remainder', '4')
    expect(screen.getByTestId('team-remainder')).toHaveTextContent('+4')
  })

  it('shows one face and +2 for a 3-member roster', () => {
    render(
      <PersonaRoster roster={roster(3, ['Alpha', 'Bravo', 'Charlie'])} groupId="squad" />,
    )
    const el = screen.getByTestId('declared-roster')
    expect(el).toHaveAttribute('data-stack-count', '1')
    expect(el).toHaveAttribute('data-remainder', '2')
    expect(screen.getByTestId('team-remainder')).toHaveTextContent('+2')
  })

  it('shows one face with no remainder for a duo roster', () => {
    render(<PersonaRoster roster={roster(2, ['Alpha', 'Bravo'])} groupId="squad" />)
    const el = screen.getByTestId('declared-roster')
    // A one-face row is not a stack, and the remainder is the other member.
    expect(el).toHaveAttribute('data-stack-count', '1')
    expect(el).toHaveAttribute('data-remainder', '1')
    expect(screen.getByTestId('team-remainder')).toHaveTextContent('+1')
  })

  it('names the remainder in the accessible label so it is not a bare glyph', () => {
    render(<PersonaRoster roster={roster(3, ['Alpha', 'Bravo', 'Charlie'])} groupId="squad" />)
    expect(screen.getByTestId('declared-roster')).toHaveAttribute(
      'aria-label',
      expect.stringMatching(/\+2/),
    )
  })

  it('does not invent a remainder for a single-member roster', () => {
    render(<PersonaRoster roster={roster(1, ['Alpha'])} groupId="squad" />)
    const el = screen.getByTestId('declared-roster')
    expect(el).toHaveAttribute('data-remainder', '0')
    expect(screen.queryByTestId('team-remainder')).not.toBeInTheDocument()
  })
})
