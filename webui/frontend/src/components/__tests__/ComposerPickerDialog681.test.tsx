/**
 * #681 — the composer picker dialog renders the state machine.
 *
 * Opening lands on the provider stage; picking a provider shows its default
 * row first (accept without scrolling); Enter accepts the highlighted row;
 * Esc backs out exactly one stage (second Esc closes); the breadcrumb shows
 * where you are and jumps back.
 */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import ComposerPickerDialog from '../ComposerPickerDialog'
import type { ComposerProviderOption } from '../../lib/composerPicker'
import type { ModelSearchOption } from '../../lib/modelSearch'

const providers: ComposerProviderOption[] = [
  { id: 'api', label: 'API gateway', kind: 'api', defaultOptionId: 'prof-default' },
  { id: 'cli:codex', label: 'codex', kind: 'cli' },
]

const apiOptions: ModelSearchOption[] = [
  { id: 'prof-default', label: 'Default profile' },
  { id: 'prof-a', label: 'Profile A' },
]

function renderDialog(overrides: Partial<Parameters<typeof ComposerPickerDialog>[0]> = {}) {
  const onPick = vi.fn()
  const onClose = vi.fn()
  const view = render(
    <ComposerPickerDialog
      open
      providers={providers}
      getProviderOptions={() => apiOptions}
      onPick={onPick}
      onClose={onClose}
      {...overrides}
    />,
  )
  return { onPick, onClose, view }
}

describe('#681 ComposerPickerDialog', () => {
  it('opens on the provider stage and filters by query', () => {
    renderDialog()
    expect(screen.getByText('API gateway')).toBeTruthy()
    fireEvent.change(screen.getByTestId('composer-picker-input'), {
      target: { value: 'codex' },
    })
    expect(screen.queryByText('API gateway')).toBeNull()
    expect(screen.getByText('codex')).toBeTruthy()
  })

  it('stage 2 shows the breadcrumb and the Use-default row first', () => {
    renderDialog()
    fireEvent.click(screen.getByText('API gateway'))
    expect(screen.getByTestId('composer-picker-breadcrumb').textContent).toContain(
      'Providers › API gateway',
    )
    const rows = screen
      .getAllByTestId('composer-picker-row')
      .map((el) => el.textContent)
    expect(rows[0]).toContain('Use default for API gateway')
    expect(rows).toHaveLength(3) // default + 2 options
  })

  it('Enter on the highlighted default row accepts the default (option = null)', () => {
    const { onPick } = renderDialog()
    fireEvent.click(screen.getByText('codex'))
    fireEvent.keyDown(screen.getByTestId('composer-picker-input'), { key: 'Enter' })
    expect(onPick).toHaveBeenCalledWith(providers[1], null)
  })

  it('clicking a specific option picks it', () => {
    const { onPick } = renderDialog()
    fireEvent.click(screen.getByText('API gateway'))
    fireEvent.click(screen.getByText('Profile A'))
    expect(onPick).toHaveBeenCalledWith(providers[0], apiOptions[1])
  })

  it('Esc backs out one stage; Esc again closes', () => {
    const { onClose } = renderDialog()
    fireEvent.click(screen.getByText('API gateway'))
    fireEvent.keyDown(screen.getByTestId('composer-picker-input'), { key: 'Escape' })
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByText('API gateway')).toBeTruthy() // back on stage 1
    fireEvent.keyDown(screen.getByTestId('composer-picker-input'), { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('breadcrumb click jumps back to providers without closing', () => {
    const { onClose } = renderDialog()
    fireEvent.click(screen.getByText('API gateway'))
    fireEvent.click(screen.getByTestId('composer-picker-breadcrumb-back'))
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByText('codex')).toBeTruthy()
  })

  it('renders nothing when closed', () => {
    renderDialog({ open: false })
    expect(screen.queryByTestId('composer-picker')).toBeNull()
  })
})
