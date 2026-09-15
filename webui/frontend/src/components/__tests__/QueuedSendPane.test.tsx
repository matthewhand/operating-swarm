import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { QueuedSendPane } from '../QueuedSendPane'
import {
  QUEUED_PANE_MAX_HEIGHT_CLASS,
  type QueuedSendRow,
} from '../../lib/chatQueue'

function row(id: string, text: string): QueuedSendRow {
  return { id, text, createdAt: 1 }
}

describe('QueuedSendPane (REQ-90)', () => {
  it('renders nothing when the queue is empty', () => {
    const { container } = render(
      <QueuedSendPane
        rows={[]}
        onChangeText={vi.fn()}
        onDelete={vi.fn()}
        onHoldIdsChange={vi.fn()}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('caps the pane at one-third and lists labelled queued rows', () => {
    const many = Array.from({ length: 12 }, (_, index) =>
      row(`q${index}`, `queued follow-up ${index}`),
    )
    render(
      <QueuedSendPane
        rows={many}
        maxHeightPx={300}
        onChangeText={vi.fn()}
        onDelete={vi.fn()}
        onHoldIdsChange={vi.fn()}
      />,
    )
    const pane = screen.getByTestId('queued-send-pane')
    expect(pane).toHaveClass('os-queued-pane')
    expect(pane).toHaveClass(QUEUED_PANE_MAX_HEIGHT_CLASS)
    expect(pane).toHaveClass('overflow-y-auto')
    expect(pane.style.maxHeight).toBe('300px')
    expect(screen.getAllByTestId('queued-row')).toHaveLength(12)
    expect(screen.getAllByText('Queued').length).toBe(12)
    expect(screen.getAllByTestId('queued-row')[0]).toHaveAttribute('data-status', 'queued')
  })

  it('edits on click and saves the new text on blur', () => {
    const onChangeText = vi.fn()
    const onHoldIdsChange = vi.fn()
    render(
      <QueuedSendPane
        rows={[row('q1', 'original')]}
        onChangeText={onChangeText}
        onDelete={vi.fn()}
        onHoldIdsChange={onHoldIdsChange}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'original' }))
    expect(onHoldIdsChange).toHaveBeenCalledWith(['q1'])
    const editor = screen.getByRole('textbox', { name: 'Edit queued message' })
    fireEvent.change(editor, { target: { value: 'revised' } })
    fireEvent.blur(editor)
    expect(onChangeText).toHaveBeenCalledWith('q1', 'revised')
  })

  it('deletes a queued row so it never sends', () => {
    const onDelete = vi.fn()
    render(
      <QueuedSendPane
        rows={[row('q1', 'drop me')]}
        onChangeText={vi.fn()}
        onDelete={onDelete}
        onHoldIdsChange={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Remove queued message' }))
    expect(onDelete).toHaveBeenCalledWith('q1')
  })
})

// #198 — 80-char hover-reveal previews + enter-to-interrupt hint
describe('QueuedSendPane (#198 preview + interrupt hint)', () => {
  it('truncates previews to 80 chars with fade class and full text on hover', () => {
    render(
      <QueuedSendPane
        rows={[row('q1', `${'x'.repeat(120)} tail`)]}
        onChangeText={vi.fn()}
        onDelete={vi.fn()}
        onHoldIdsChange={vi.fn()}
      />,
    )
    const text = screen.getByRole('button', { name: /x{20}/ })
    expect(text).toHaveClass('is-truncated')
    expect(text).toHaveAttribute('title', `${'x'.repeat(120)} tail`)
    expect(text.textContent).toBe(`${'x'.repeat(80)}…`)
  })

  it('leaves short previews untouched', () => {
    render(
      <QueuedSendPane
        rows={[row('q1', 'short and sweet')]}
        onChangeText={vi.fn()}
        onDelete={vi.fn()}
        onHoldIdsChange={vi.fn()}
      />,
    )
    const text = screen.getByRole('button', { name: 'short and sweet' })
    expect(text).not.toHaveClass('is-truncated')
    expect(text.textContent).toBe('short and sweet')
  })

  it('shows the enter-to-interrupt hint on the top row only when interruptible', () => {
    const props = {
      rows: [row('q1', 'first'), row('q2', 'second')],
      onChangeText: vi.fn(),
      onDelete: vi.fn(),
      onHoldIdsChange: vi.fn(),
    }
    const { rerender } = render(<QueuedSendPane {...props} />)
    expect(screen.queryByTestId('queued-interrupt-hint')).toBeNull()
    rerender(
      <QueuedSendPane {...props} interruptible={true} />,
    )
    expect(screen.getAllByTestId('queued-interrupt-hint')).toHaveLength(1)
  })

  // #223 — "Clear all" affordance
  it('hides Clear all for a single row and with no handler', () => {
    const { rerender } = render(
      <QueuedSendPane
        rows={[row('q1', 'only row')]}
        onChangeText={vi.fn()}
        onDelete={vi.fn()}
        onHoldIdsChange={vi.fn()}
        onClearAll={vi.fn()}
      />,
    )
    expect(screen.queryByTestId('queued-clear-all')).toBeNull()
    rerender(
      <QueuedSendPane
        rows={[row('q1', 'first'), row('q2', 'second')]}
        onChangeText={vi.fn()}
        onDelete={vi.fn()}
        onHoldIdsChange={vi.fn()}
      />,
    )
    expect(screen.queryByTestId('queued-clear-all')).toBeNull()
  })

  it('Clear all invokes the handler once', () => {
    const onClearAll = vi.fn()
    render(
      <QueuedSendPane
        rows={[row('q1', 'first'), row('q2', 'second')]}
        onChangeText={vi.fn()}
        onDelete={vi.fn()}
        onHoldIdsChange={vi.fn()}
        onClearAll={onClearAll}
      />,
    )
    fireEvent.click(screen.getByTestId('queued-clear-all'))
    expect(onClearAll).toHaveBeenCalledTimes(1)
  })
})
