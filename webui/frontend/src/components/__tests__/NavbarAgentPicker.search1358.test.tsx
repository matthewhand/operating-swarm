/**
 * #1358 — the navbar agent picker is a search popup. The text filter runs on
 * the provider-scoped rows, so searching can never reveal a foreign provider
 * (nor the default inference profile).
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import NavbarAgentPicker, {
  NAVBAR_AGENT_PICKER_MENU_TESTID,
  NAVBAR_AGENT_PICKER_SEARCH_TESTID,
} from '../NavbarAgentPicker'

const TF_AGENTS = [
  { id: 'agent-1', label: 'orchestrator', provider: 'remote:trueforge' },
  { id: 'agent-2', label: 'coder', provider: 'remote:trueforge' },
  { id: 'agent-3', label: 'grok', provider: 'remote:hermes' },
]

function open() {
  fireEvent.click(screen.getByTestId('os-navbar-agent-picker'))
}

describe('#1358 NavbarAgentPicker search popup', () => {
  it('shows a search input and filters the provider-scoped agents', () => {
    render(<NavbarAgentPicker agents={TF_AGENTS} selectedId="agent-1" />)
    open()

    const search = screen.getByTestId(NAVBAR_AGENT_PICKER_SEARCH_TESTID)
    expect(search).toBeInTheDocument()
    // Scoped to TrueForge: the hermes row is never present.
    expect(screen.queryByTestId('os-navbar-agent-option-agent-3')).toBeNull()

    fireEvent.change(search, { target: { value: 'code' } })
    expect(screen.getByTestId('os-navbar-agent-option-agent-2')).toBeInTheDocument()
    expect(screen.queryByTestId('os-navbar-agent-option-agent-1')).toBeNull()

    fireEvent.change(search, { target: { value: '' } })
    expect(screen.getByTestId('os-navbar-agent-option-agent-1')).toBeInTheDocument()
  })

  it('never reveals a foreign provider even when the query matches it', () => {
    render(
      <NavbarAgentPicker agents={TF_AGENTS} selectedId="agent-1" provider="remote:trueforge" />,
    )
    open()
    fireEvent.change(screen.getByTestId(NAVBAR_AGENT_PICKER_SEARCH_TESTID), {
      target: { value: 'grok' },
    })
    expect(screen.queryByTestId('os-navbar-agent-option-agent-3')).toBeNull()
    expect(screen.getByText('No matching agents')).toBeInTheDocument()
    expect(screen.getByTestId(NAVBAR_AGENT_PICKER_MENU_TESTID)).toHaveAttribute(
      'data-provider',
      'remote:trueforge',
    )
  })

  it('reports the pick from the search popup', () => {
    const onSelect = vi.fn()
    render(<NavbarAgentPicker agents={TF_AGENTS} selectedId="agent-1" onSelect={onSelect} />)
    open()
    fireEvent.change(screen.getByTestId(NAVBAR_AGENT_PICKER_SEARCH_TESTID), {
      target: { value: 'coder' },
    })
    fireEvent.click(screen.getByTestId('os-navbar-agent-option-agent-2'))
    expect(onSelect).toHaveBeenCalledWith('agent-2', undefined)
    expect(screen.queryByTestId(NAVBAR_AGENT_PICKER_MENU_TESTID)).toBeNull()
  })

  it('closes on Escape from the search input (handler preserved)', () => {
    render(<NavbarAgentPicker agents={TF_AGENTS} selectedId="agent-1" />)
    open()
    const search = screen.getByTestId(NAVBAR_AGENT_PICKER_SEARCH_TESTID)
    fireEvent.keyDown(search, { key: 'Escape' })
    // The document-level Escape listener also fires; assert the popup is gone.
    expect(screen.queryByTestId(NAVBAR_AGENT_PICKER_MENU_TESTID)).toBeNull()
  })
})
