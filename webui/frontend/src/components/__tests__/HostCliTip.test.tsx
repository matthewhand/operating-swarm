import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { HostCliTip } from '../HostCliTip'
import { OPEN_SETTINGS_EVENT } from '../settings/kernel'
import type { OpenSettingsDetail } from '../settings/kernel'

function renderTip(over: Partial<React.ComponentProps<typeof HostCliTip>> = {}) {
  const props = {
    cliName: 'opencode',
    onDismiss: vi.fn(),
    onNeverShowAgain: vi.fn(),
    ...over,
  }
  render(<HostCliTip {...props} />)
  return props
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('HostCliTip', () => {
  it('states the detected CLI by name (Success #1)', () => {
    renderTip()
    const tip = screen.getByTestId('host-cli-tip')
    expect(screen.getByTestId('host-cli-tip-title')).toHaveTextContent('opencode detected')
    expect(screen.getByTestId('host-cli-tip-body')).toHaveTextContent('opencode')
    expect(tip).toHaveAttribute('data-cli', 'opencode')
  })

  it('offers an Add provider button that deep-links to CLI agents settings (Success #2)', () => {
    const opened: Array<OpenSettingsDetail | undefined> = []
    const listener = (e: Event) => opened.push((e as CustomEvent<OpenSettingsDetail>).detail)
    window.addEventListener(OPEN_SETTINGS_EVENT, listener)
    try {
      renderTip()
      const add = screen.getByTestId('host-cli-tip-add')
      expect(add).toHaveTextContent('Add provider')
      fireEvent.click(add)
      // addCliName is what prefills the add form for the detected CLI.
      expect(opened).toEqual([{ section: 'cli-agents', addCliName: 'opencode' }])
    } finally {
      window.removeEventListener(OPEN_SETTINGS_EVENT, listener)
    }
  })

  it('separates the session dismiss (X) from the persistent opt-out (Success #3)', () => {
    const props = renderTip()
    fireEvent.click(screen.getByTestId('host-cli-tip-dismiss'))
    expect(props.onDismiss).toHaveBeenCalledTimes(1)
    expect(props.onNeverShowAgain).not.toHaveBeenCalled()

    fireEvent.click(screen.getByTestId('host-cli-tip-never'))
    expect(props.onNeverShowAgain).toHaveBeenCalledTimes(1)
  })

  it('is an inline status banner, never a blocking dialog (Success #5)', () => {
    renderTip()
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('labels the dismiss button for screen readers', () => {
    renderTip()
    expect(screen.getByLabelText('Dismiss opencode detected')).toBeInTheDocument()
  })
})
