/**
 * #1202 — the `[ 🤖 Agent ]` navbar shell. Supported → active; unsupported →
 * mounted but greyed with a capability-aware tooltip and an inert click.
 *
 * #1202 follow-up — the enabled control is a picker of the *available agents*
 * to switch to (never the current agent's configuration).
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import NavbarAgentPicker, {
  NAVBAR_AGENT_PICKER_MENU_TESTID,
} from '../NavbarAgentPicker'

const AGENTS = [
  { id: 'codey', label: 'Codey', kind: 'api' },
  { id: 'agy', label: 'Agy', kind: 'cli' },
]

describe('#1202 NavbarAgentPicker', () => {
  it('is active when the seat supports agents', () => {
    render(<NavbarAgentPicker agents={AGENTS} />)
    const btn = screen.getByTestId('os-navbar-agent-picker')
    expect(btn).not.toBeDisabled()
    expect(btn).toHaveAttribute('data-disabled', 'false')
    expect(btn).toHaveAttribute('aria-haspopup', 'menu')
  })

  it('lists the available agents and reports the pick (never the config)', () => {
    const onSelect = vi.fn()
    render(<NavbarAgentPicker agents={AGENTS} selectedId="codey" onSelect={onSelect} />)

    expect(screen.queryByTestId(NAVBAR_AGENT_PICKER_MENU_TESTID)).toBeNull()
    fireEvent.click(screen.getByTestId('os-navbar-agent-picker'))
    const menu = screen.getByTestId(NAVBAR_AGENT_PICKER_MENU_TESTID)
    expect(menu).toBeInTheDocument()

    const rows = screen.getAllByRole('menuitem')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('Codey')
    // The current agent is marked, not treated as a config surface.
    expect(screen.getByTestId('os-navbar-agent-option-codey')).toHaveAttribute(
      'aria-current',
      'true',
    )

    fireEvent.click(screen.getByTestId('os-navbar-agent-option-agy'))
    expect(onSelect).toHaveBeenCalledWith('agy', 'cli')
    expect(screen.queryByTestId(NAVBAR_AGENT_PICKER_MENU_TESTID)).toBeNull()
  })

  it('lists a remote seat’s own agents (no palette) and reports the pick', () => {
    const onSelect = vi.fn()
    render(
      <NavbarAgentPicker
        agents={[{ id: 'hermes-agent', label: 'hermes-agent' }]}
        onSelect={onSelect}
      />,
    )
    fireEvent.click(screen.getByTestId('os-navbar-agent-picker'))
    expect(screen.getByTestId('os-navbar-agent-option-hermes-agent')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('os-navbar-agent-option-hermes-agent'))
    // Remote agents carry no declared seat kind — the id is the routing target.
    expect(onSelect).toHaveBeenCalledWith('hermes-agent', undefined)
  })

  it('greys out with a capability-aware tooltip and inert click when unsupported', () => {
    const onSelect = vi.fn()
    render(
      <NavbarAgentPicker
        disabled
        reason="Agent selection is not supported by Grok"
        agents={AGENTS}
        onSelect={onSelect}
      />,
    )
    const btn = screen.getByTestId('os-navbar-agent-picker')
    expect(btn).toBeDisabled()
    expect(btn).toHaveAttribute('data-disabled', 'true')
    expect(btn).toHaveAttribute('data-tip', 'Agent selection is not supported by Grok')
    expect(btn).toHaveClass('opacity-40')
    expect(btn).toHaveClass('cursor-not-allowed')
    fireEvent.click(btn)
    expect(onSelect).not.toHaveBeenCalled()
    expect(screen.queryByTestId(NAVBAR_AGENT_PICKER_MENU_TESTID)).toBeNull()
  })
})
