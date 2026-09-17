import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CliSessionRecoveryBanner } from '../CliSessionRecoveryBanner'
import { CLI_SESSION_RECOVERY_MESSAGE } from '../../lib/cliSessionRecovery'

describe('CliSessionRecoveryBanner', () => {
  it('renders recovery copy and drives Start Fresh, Retry, and Clear History', () => {
    const onStartFresh = vi.fn()
    const onRetry = vi.fn()
    const onClearHistory = vi.fn()
    render(
      <CliSessionRecoveryBanner
        onStartFresh={onStartFresh}
        onRetry={onRetry}
        onClearHistory={onClearHistory}
      />,
    )
    const banner = screen.getByTestId('cli-session-recovery')
    expect(banner).toHaveTextContent(CLI_SESSION_RECOVERY_MESSAGE)
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('cli-session-recovery-fresh'))
    fireEvent.click(screen.getByTestId('cli-session-recovery-retry'))
    fireEvent.click(screen.getByTestId('cli-session-recovery-clear'))
    expect(onStartFresh).toHaveBeenCalledTimes(1)
    expect(onRetry).toHaveBeenCalledTimes(1)
    expect(onClearHistory).toHaveBeenCalledTimes(1)
  })
})
