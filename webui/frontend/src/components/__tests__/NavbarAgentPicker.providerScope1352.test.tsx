/**
 * #1352 — the navbar agent picker lists only agents from the **selected
 * agent's provider** (as configured in Edit agent), never the default
 * inference profile.
 *
 * The provider scope rides on each option row (`provider`); the picker derives
 * the current scope from the selected row (or an explicit `provider` prop) and
 * filters. Rows without provider metadata keep the historical show-all
 * behaviour so unmigrated callers do not regress.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import NavbarAgentPicker from '../NavbarAgentPicker'
import { NAVBAR_AGENT_PICKER_MENU_TESTID } from '../NavbarAgentPicker'

const AGENTS = [
  { id: 'opencode-a', label: 'Opencode A', kind: 'cli', provider: 'cli:opencode' },
  { id: 'opencode-b', label: 'Opencode B', kind: 'cli', provider: 'cli:opencode' },
  { id: 'codex-a', label: 'Codex A', kind: 'cli', provider: 'cli:codex' },
  { id: 'codey', label: 'Codey', kind: 'api', provider: 'api:api' },
]

function open() {
  fireEvent.click(screen.getByTestId('os-navbar-agent-picker'))
}

describe('#1352 NavbarAgentPicker provider scoping', () => {
  it('lists only the selected agent’s provider (opencode)', () => {
    render(<NavbarAgentPicker agents={AGENTS} selectedId="opencode-a" />)
    open()
    expect(screen.getByTestId('os-navbar-agent-option-opencode-a')).toBeInTheDocument()
    expect(screen.getByTestId('os-navbar-agent-option-opencode-b')).toBeInTheDocument()
    // Foreign provider + the API/default profile are never offered.
    expect(screen.queryByTestId('os-navbar-agent-option-codex-a')).toBeNull()
    expect(screen.queryByTestId('os-navbar-agent-option-codey')).toBeNull()
    expect(screen.getByTestId(NAVBAR_AGENT_PICKER_MENU_TESTID)).toHaveAttribute(
      'data-provider',
      'cli:opencode',
    )
  })

  it('switching the selected agent’s provider changes what the picker shows', () => {
    const { rerender } = render(
      <NavbarAgentPicker agents={AGENTS} selectedId="opencode-a" />,
    )
    open()
    expect(screen.queryByTestId('os-navbar-agent-option-codex-a')).toBeNull()
    fireEvent.keyDown(document, { key: 'Escape' })

    // Edit agent switched the provider to codex — the same list now scopes to
    // codex and opencode disappears.
    rerender(<NavbarAgentPicker agents={AGENTS} selectedId="codex-a" />)
    open()
    expect(screen.getByTestId('os-navbar-agent-option-codex-a')).toBeInTheDocument()
    expect(screen.queryByTestId('os-navbar-agent-option-opencode-a')).toBeNull()
    expect(screen.queryByTestId('os-navbar-agent-option-codey')).toBeNull()
  })

  it('an explicit provider prop outranks the selected row (default profile never leaks)', () => {
    render(
      <NavbarAgentPicker agents={AGENTS} selectedId="opencode-a" provider="api:api" />,
    )
    open()
    expect(screen.getByTestId('os-navbar-agent-option-codey')).toBeInTheDocument()
    expect(screen.queryByTestId('os-navbar-agent-option-opencode-a')).toBeNull()
    expect(screen.getByTestId(NAVBAR_AGENT_PICKER_MENU_TESTID)).toHaveAttribute(
      'data-provider',
      'api:api',
    )
  })

  it('keeps every agent when no row declares a provider (back-compat)', () => {
    render(
      <NavbarAgentPicker
        agents={[
          { id: 'codey', label: 'Codey', kind: 'api' },
          { id: 'agy', label: 'Agy', kind: 'cli' },
        ]}
        selectedId="codey"
      />,
    )
    open()
    expect(screen.getByTestId('os-navbar-agent-option-codey')).toBeInTheDocument()
    expect(screen.getByTestId('os-navbar-agent-option-agy')).toBeInTheDocument()
  })
})
