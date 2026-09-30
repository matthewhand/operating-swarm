/**
 * #1202 — the `[ 💬 Session ]` navbar shell. Supported → the reused switcher
 * child renders; unsupported → greyed shell with a capability-aware tooltip,
 * the child never mounts, and the click is inert.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import NavbarSessionPicker from '../NavbarSessionPicker'

describe('#1202 NavbarSessionPicker', () => {
  it('renders the reused switcher when the seat supports sessions', () => {
    const onSelect = vi.fn()
    render(
      <NavbarSessionPicker>
        <button type="button" data-testid="reused-session-switcher" onClick={onSelect}>
          sessions
        </button>
      </NavbarSessionPicker>,
    )
    expect(screen.queryByTestId('os-navbar-session-picker')).toBeNull()
    fireEvent.click(screen.getByTestId('reused-session-switcher'))
    expect(onSelect).toHaveBeenCalledTimes(1)
  })

  it('greys out with a capability-aware tooltip and never mounts the switcher when unsupported', () => {
    render(
      <NavbarSessionPicker
        disabled
        reason="Rakazo is stateless and does not support persistent sessions"
      >
        <button type="button" data-testid="reused-session-switcher">
          sessions
        </button>
      </NavbarSessionPicker>,
    )
    const btn = screen.getByTestId('os-navbar-session-picker')
    expect(btn).toBeDisabled()
    expect(btn).toHaveAttribute('data-disabled', 'true')
    expect(btn).toHaveAttribute(
      'data-tip',
      'Rakazo is stateless and does not support persistent sessions',
    )
    expect(btn).toHaveClass('opacity-40')
    expect(btn).toHaveClass('cursor-not-allowed')
    expect(screen.queryByTestId('reused-session-switcher')).toBeNull()
  })

  it('mounts the remote switcher child verbatim when the remote declares sessions', () => {
    render(
      <NavbarSessionPicker>
        <button type="button" data-testid="reused-session-switcher">
          hermes sessions
        </button>
      </NavbarSessionPicker>,
    )
    // No wrapper shell, no disabled button — the reused switcher owns the click.
    expect(screen.queryByTestId('os-navbar-session-picker')).toBeNull()
    expect(screen.getByTestId('reused-session-switcher')).toBeInTheDocument()
  })
})
