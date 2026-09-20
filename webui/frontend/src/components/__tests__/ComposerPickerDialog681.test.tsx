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
    expect(screen.getByTestId('composer-picker-breadcrumb')).toHaveTextContent('API gateway')
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

  it('Esc works after a mouse pick moved focus off the input (live #681 finding)', () => {
    const { onClose } = renderDialog()
    fireEvent.click(screen.getByText('API gateway'))
    // The click focused the row button; Escape must still reach the dialog.
    fireEvent.keyDown(screen.getByTestId('composer-picker'), { key: 'Escape' })
    expect(onClose).not.toHaveBeenCalled()
    // #837: stage 1 has no breadcrumb header — the filter input leads.
    expect(screen.queryByTestId('composer-picker-breadcrumb')).toBeNull()
    fireEvent.keyDown(screen.getByTestId('composer-picker'), { key: 'Escape' })
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

describe('#803 — auto-pick on exactly-one non-session option', () => {
  const single: ComposerProviderOption[] = [
    { id: 'cli:grok', label: 'grok', kind: 'cli' },
    { id: 'cli:codex', label: 'codex', kind: 'cli' },
  ]

  function renderAuto(overrides: Partial<Parameters<typeof ComposerPickerDialog>[0]> = {}) {
    const onPick = vi.fn()
    const onClose = vi.fn()
    render(
      <ComposerPickerDialog
        open
        providers={single}
        getProviderOptions={() => []}
        onPick={onPick}
        onClose={onClose}
        {...overrides}
      />,
    )
    return { onPick, onClose }
  }

  it('a provider with 0 options still descends — the Use-default accept is the #681/#804 contract', () => {
    const { onPick, onClose } = renderAuto()
    fireEvent.click(screen.getByText('grok'))
    // Stage 2 with only the default row: the explicit accept resolves.
    fireEvent.click(screen.getByText('Use default'))
    expect(onPick).toHaveBeenCalledTimes(1)
    expect(onPick).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'cli:grok', kind: 'cli' }),
      null,
    )
    expect(onClose).toHaveBeenCalled()
  })

  it('a lone session-tagged option still descends and surfaces via onPick — the caller routes the resume (#711)', () => {
    const { onPick } = renderAuto({
      getProviderOptions: (p) =>
        p.id === 'cli:codex' ? [{ id: 'codex:main', label: 'codex main session', tag: 'session' }] : [],
    })
    fireEvent.click(screen.getByText('codex'))
    fireEvent.click(screen.getByText('codex main session'))
    expect(onPick).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'cli:codex' }),
      expect.objectContaining({ id: 'codex:main', tag: 'session' }),
    )
  })

  it('a provider with exactly 1 option auto-picks that option', () => {
    const { onPick, onClose } = renderAuto({
      getProviderOptions: (p) =>
        p.id === 'cli:codex' ? [{ id: 'grok-4', label: 'grok-4', tag: 'model' }] : [],
    })
    fireEvent.click(screen.getByText('codex'))
    expect(onPick).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'cli:codex' }),
      expect.objectContaining({ id: 'grok-4' }),
    )
    expect(onClose).toHaveBeenCalled()
  })

  it('a provider with >= 2 options still opens stage 2', () => {
    const { onPick, onClose } = renderAuto({
      getProviderOptions: (p) =>
        p.id === 'cli:codex'
          ? [
              { id: 'a', label: 'Model A', tag: 'model' },
              { id: 'b', label: 'Model B', tag: 'model' },
            ]
          : [],
    })
    fireEvent.click(screen.getByText('codex'))
    expect(onPick).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByTestId('composer-picker-breadcrumb').textContent).toContain('codex')
  })
})
