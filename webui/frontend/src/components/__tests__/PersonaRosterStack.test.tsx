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

describe('#98: declared PersonaRoster follows the team stack plan', () => {
  it('shows all faces for a roster of 4 — no remainder', () => {
    render(
      <PersonaRoster
        roster={roster(4, ['Alpha', 'Bravo', 'Charlie', 'Delta'])}
        groupId="squad"
      />,
    )
    const el = screen.getByTestId('declared-roster')
    expect(el).toHaveAttribute('data-stack-count', '4')
    expect(el).toHaveAttribute('data-remainder', '0')
    expect(el.querySelectorAll('[data-testid="os-stacked-avatar"]')).toHaveLength(4)
  })

  it('collapses a roster of 5 to 2 faces + remainder 3', () => {
    render(
      <PersonaRoster
        roster={roster(5, ['Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo'])}
        groupId="squad"
      />,
    )
    const el = screen.getByTestId('declared-roster')
    expect(el).toHaveAttribute('data-stack-count', '2')
    expect(el).toHaveAttribute('data-remainder', '3')
    expect(el.querySelectorAll('[data-testid="os-stacked-avatar"]')).toHaveLength(2)
  })

  it('keeps a 3-member roster fully visible (2 faces would be wrong here)', () => {
    render(
      <PersonaRoster roster={roster(3, ['Alpha', 'Bravo', 'Charlie'])} groupId="squad" />,
    )
    const el = screen.getByTestId('declared-roster')
    expect(el).toHaveAttribute('data-stack-count', '3')
    expect(el).toHaveAttribute('data-remainder', '0')
  })

  it('duo roster stays a stack of 2 without a remainder', () => {
    render(<PersonaRoster roster={roster(2, ['Alpha', 'Bravo'])} groupId="squad" />)
    const el = screen.getByTestId('declared-roster')
    expect(el).toHaveAttribute('data-stack-count', '2')
    expect(el).toHaveAttribute('data-remainder', '0')
  })
})
