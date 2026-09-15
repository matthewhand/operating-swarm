import { describe, expect, it, vi, type Mock } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import CliSessionPicker, { type CliSessionPickerProps } from '../CliSessionPicker'
import type { CliProviderSession } from '../../lib/cliSessions'

function session(
  id: string,
  title: string,
  snippet: string,
  updatedAt: string,
  source: CliProviderSession['source'] = 'provider',
): CliProviderSession {
  return { id, title, snippet, updated_at: updatedAt, source }
}

const FIXTURE: CliProviderSession[] = [
  session('sid-1', 'First', 'alpha work', '2026-09-05T12:00:00Z'),
  session('sid-2', 'Second', 'bravo work', '2026-09-05T11:00:00Z'),
  session('sid-3', 'Third', 'charlie work', '2026-09-04T12:00:00Z'),
]

function renderPicker(extras: Partial<CliSessionPickerProps> = {}) {
  const onSelect = extras.onSelect ?? vi.fn()
  const onClose = extras.onClose ?? vi.fn()
  const onStartNew = extras.onStartNew ?? vi.fn()
  return {
    onSelect,
    onClose,
    onStartNew,
    ...render(
      <CliSessionPicker
        open
        agentName="cli_agent"
        cli="grok"
        sessions={FIXTURE}
        canList
        onClose={onClose}
        onSelect={onSelect}
        onStartNew={onStartNew}
        {...extras}
      />,
    ),
  }
}

describe('CliSessionPicker', () => {
  it('lists provider sessions and filters by snippet', () => {
    renderPicker()
    const dialog = screen.getByRole('dialog', { name: 'cli_agent sessions' })
    const options = within(dialog).getAllByRole('option')
    expect(options).toHaveLength(3)
    expect(options.map((row) => row.getAttribute('data-session-id'))).toEqual([
      'sid-1',
      'sid-2',
      'sid-3',
    ])

    fireEvent.change(screen.getByRole('combobox', { name: /Filter cli_agent sessions/i }), {
      target: { value: 'bravo' },
    })
    const narrowed = within(dialog).getAllByRole('option')
    expect(narrowed).toHaveLength(1)
    expect(narrowed[0]).toHaveAttribute('data-session-id', 'sid-2')
  })

  it('offers a paste-id row for an arbitrary session id', () => {
    const { onSelect } = renderPicker()
    fireEvent.change(screen.getByRole('combobox', { name: /Filter cli_agent sessions/i }), {
      target: { value: 'pasted-session-99' },
    })
    const paste = screen.getByRole('option', { name: /Use session pasted-session-99/i })
    expect(paste).toBeInTheDocument()
    fireEvent.click(paste)
    expect(onSelect).toHaveBeenCalledTimes(1)
    expect((onSelect as Mock<(s: CliProviderSession) => void>).mock.calls[0][0].id).toBe('pasted-session-99')
  })

  it('navigates with the keyboard and selects on Enter', () => {
    const { onSelect } = renderPicker()
    fireEvent.keyDown(window, { key: 'ArrowDown' })
    fireEvent.keyDown(window, { key: 'Enter' })
    expect(onSelect).toHaveBeenCalledTimes(1)
    expect((onSelect as Mock<(s: CliProviderSession) => void>).mock.calls[0][0].id).toBe('sid-2')
  })

  it('shows honest empty copy when the CLI cannot list', () => {
    renderPicker({ sessions: [], canList: false, emptyReason: "This CLI can't list sessions" })
    expect(screen.getByTestId('cli-session-empty')).toHaveTextContent(
      "This CLI can't list sessions",
    )
  })

  it('shows No sessions found when listable but empty', () => {
    renderPicker({ sessions: [], canList: true })
    expect(screen.getByTestId('cli-session-empty')).toHaveTextContent('No sessions found')
  })

  it('ends with a divider then Manage Session', () => {
    const onManageSession = vi.fn()
    const { onClose } = renderPicker({ onManageSession })
    const divider = screen.getByTestId('manage-surface-divider')
    expect(divider).toHaveAttribute('role', 'separator')
    const manage = screen.getByRole('button', { name: 'Manage Session' })
    expect(manage.compareDocumentPosition(divider) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy()
    fireEvent.click(manage)
    expect(onManageSession).toHaveBeenCalledTimes(1)
    expect(onClose).toHaveBeenCalled()
  })

  it('Start new session fires onStartNew', () => {
    const { onStartNew, onClose } = renderPicker()
    fireEvent.click(screen.getByTestId('cli-session-start-new'))
    expect(onStartNew).toHaveBeenCalledTimes(1)
    expect(onClose).toHaveBeenCalled()
  })

  it('Continue on another CLI hops the selected provider session', () => {
    const onContinueOn = vi.fn()
    const { onClose } = renderPicker({
      continueTargets: ['agy', 'opencode'],
      onContinueOn,
    })
    const select = screen.getByRole('combobox', { name: 'Continue on CLI' })
    fireEvent.change(select, { target: { value: 'agy' } })
    expect(onContinueOn).toHaveBeenCalledTimes(1)
    expect(onContinueOn.mock.calls[0][0].id).toBe('sid-1')
    expect(onContinueOn.mock.calls[0][1]).toBe('agy')
    expect(onClose).toHaveBeenCalled()
  })
})
