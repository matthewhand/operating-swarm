/**
 * #499 — when the failure names a configuration, the banner's primary action
 * opens Settings on that section; the session actions stay secondary. Without
 * a target the banner is unchanged (no dead buttons, no regression).
 */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CliSessionRecoveryBanner } from '../CliSessionRecoveryBanner'
import { CLI_SESSION_RECOVERY_MESSAGE } from '../../lib/cliSessionRecovery'

describe('CliSessionRecoveryBanner #499 configure action', () => {
  it('renders Configure as primary and deep-links to the target section', () => {
    const onConfigure = vi.fn()
    const onStartFresh = vi.fn()
    render(
      <CliSessionRecoveryBanner
        onStartFresh={onStartFresh}
        onRetry={vi.fn()}
        onClearHistory={vi.fn()}
        configTarget={{ section: 'cli-agents' }}
        onConfigure={onConfigure}
      />,
    )
    const configure = screen.getByTestId('cli-session-recovery-configure')
    expect(configure).toHaveClass('btn-primary')
    fireEvent.click(configure)
    expect(onConfigure).toHaveBeenCalledWith({ section: 'cli-agents' })
    // Session actions remain available.
    expect(screen.getByTestId('cli-session-recovery-fresh')).toBeInTheDocument()
    expect(onStartFresh).not.toHaveBeenCalled()
  })

  it('without a target renders the banner unchanged (no Configure)', () => {
    render(
      <CliSessionRecoveryBanner
        onStartFresh={vi.fn()}
        onRetry={vi.fn()}
        onClearHistory={vi.fn()}
      />,
    )
    expect(screen.getByTestId('cli-session-recovery')).toHaveTextContent(
      CLI_SESSION_RECOVERY_MESSAGE,
    )
    expect(screen.queryByTestId('cli-session-recovery-configure')).not.toBeInTheDocument()
  })
})
