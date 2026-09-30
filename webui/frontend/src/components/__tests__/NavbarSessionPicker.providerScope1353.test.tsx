/**
 * #1353 — the session shell surfaces the provider scope it is listing for, so
 * the selected provider (never the default inference profile) governs the
 * child switcher's list. The child switcher owns the actual fetch.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import NavbarSessionPicker, {
  NAVBAR_SESSION_PICKER_TESTID,
  NAVBAR_SESSION_SCOPE_TESTID,
} from '../NavbarSessionPicker'

describe('#1353 NavbarSessionPicker provider scope', () => {
  it('marks the provider scope around the reused switcher', () => {
    render(
      <NavbarSessionPicker provider="cli:opencode">
        <button type="button" data-testid="reused-session-switcher">
          sessions
        </button>
      </NavbarSessionPicker>,
    )
    expect(screen.getByTestId(NAVBAR_SESSION_SCOPE_TESTID)).toHaveAttribute(
      'data-provider',
      'cli:opencode',
    )
    expect(screen.getByTestId('reused-session-switcher')).toBeInTheDocument()
  })

  it('carries the scope on the disabled shell and mounts no switcher', () => {
    render(
      <NavbarSessionPicker disabled reason="stateless" provider="remote:hermes">
        <button type="button" data-testid="reused-session-switcher">
          sessions
        </button>
      </NavbarSessionPicker>,
    )
    const btn = screen.getByTestId(NAVBAR_SESSION_PICKER_TESTID)
    expect(btn).toHaveAttribute('data-provider', 'remote:hermes')
    expect(screen.queryByTestId('reused-session-switcher')).toBeNull()
  })
})
