import { createEvent, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { CompactSummaryCard } from '../CompactSummaryCard'

describe('CompactSummaryCard (REQ-213)', () => {
  it('right-click opens the DaisyUI menu and suppresses the browser default', () => {
    render(<CompactSummaryCard body="outer digest" meta="Replaced 2 turns" />)

    const card = screen.getByTestId('chat-summary')
    const ev = createEvent.contextMenu(card)
    fireEvent(card, ev)
    expect(ev.defaultPrevented).toBe(true)

    const menu = screen.getByTestId('compacted-card-context-menu')
    expect(menu).toHaveClass('menu')
    expect(screen.getByRole('menuitem', { name: 'Collapse' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Copy' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Remove from view' })).toHaveClass('text-error')
  })

  it('Collapse hides the summary body; Expand reveals it again', () => {
    render(<CompactSummaryCard body="outer digest" />)
    expect(screen.getByTestId('chat-summary-content')).toHaveTextContent('outer digest')

    fireEvent.contextMenu(screen.getByTestId('chat-summary'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Collapse' }))
    expect(screen.queryByTestId('chat-summary-content')).not.toBeInTheDocument()
    expect(screen.queryByTestId('compacted-card-context-menu')).not.toBeInTheDocument()

    fireEvent.contextMenu(screen.getByTestId('chat-summary'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Expand' }))
    expect(screen.getByTestId('chat-summary-content')).toHaveTextContent('outer digest')
  })

  it('Copy writes the full underlying summary text', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    render(
      <CompactSummaryCard
        body="digest"
        compacted={[{ role: 'user', text: 'Ship it' }]}
      />,
    )
    fireEvent.contextMenu(screen.getByTestId('chat-summary'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Copy' }))
    expect(writeText).toHaveBeenCalledWith('digest\n\n---\n[user]: Ship it')
  })

  it('Remove from view hides the chip without a persist callback', () => {
    render(<CompactSummaryCard body="digest" />)
    fireEvent.contextMenu(screen.getByTestId('chat-summary'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Remove from view' }))
    expect(screen.queryByTestId('chat-summary')).not.toBeInTheDocument()
  })

  it('Remove from view notifies the parent so Chat can hide without rewriting disk', () => {
    const onRemove = vi.fn()
    render(<CompactSummaryCard body="digest" onRemove={onRemove} />)
    fireEvent.contextMenu(screen.getByTestId('chat-summary'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Remove from view' }))
    expect(onRemove).toHaveBeenCalledTimes(1)
  })
})

describe('CompactSummaryCard include-in-context (#214)', () => {
  it('renders no checkbox when the toggle is not wired (system pills unchanged)', () => {
    render(<CompactSummaryCard body="digest" />)
    expect(screen.queryByTestId('summary-context-checkbox')).not.toBeInTheDocument()
    expect(screen.getByTestId('chat-summary')).not.toHaveAttribute('data-in-context')
  })

  it('defaults to ticked and renders the honest included state', () => {
    render(<CompactSummaryCard body="digest" inContext={true} onToggleContext={vi.fn()} />)
    const box = screen.getByTestId('summary-context-checkbox') as HTMLInputElement
    expect(box.checked).toBe(true)
    expect(screen.getByTestId('chat-summary')).toHaveAttribute('data-in-context', 'true')
    expect(screen.queryByTestId('summary-excluded-note')).not.toBeInTheDocument()
  })

  it('unticking calls onToggleContext(false)', () => {
    const onToggleContext = vi.fn()
    render(<CompactSummaryCard body="digest" inContext={true} onToggleContext={onToggleContext} />)
    fireEvent.click(screen.getByTestId('summary-context-checkbox'))
    expect(onToggleContext).toHaveBeenCalledWith(false)
  })

  it('excluded state is visually honest: dimmed card + note', () => {
    render(<CompactSummaryCard body="digest" inContext={false} onToggleContext={vi.fn()} />)
    expect(screen.getByTestId('summary-context-checkbox')).not.toBeChecked()
    expect(screen.getByTestId('chat-summary')).toHaveAttribute('data-in-context', 'false')
    expect(screen.getByTestId('chat-summary').className).toContain('opacity-60')
    expect(screen.getByTestId('summary-excluded-note')).toHaveTextContent(
      'Not included in chat context',
    )
  })

  it('menu offers the live include/exclude context item for summaries', () => {
    const onToggleContext = vi.fn()
    render(<CompactSummaryCard body="digest" inContext={false} onToggleContext={onToggleContext} />)
    fireEvent.contextMenu(screen.getByTestId('chat-summary'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Include in chat context' }))
    expect(onToggleContext).toHaveBeenCalledWith(true)
  })

  it('menu shows the ticked state and excludes via menu too', () => {
    const onToggleContext = vi.fn()
    render(<CompactSummaryCard body="digest" inContext={true} onToggleContext={onToggleContext} />)
    fireEvent.contextMenu(screen.getByTestId('chat-summary'))
    fireEvent.click(screen.getByRole('menuitem', { name: '✓ Included in chat context' }))
    expect(onToggleContext).toHaveBeenCalledWith(false)
  })

  it('no context item appears in the menu when the toggle is not wired', () => {
    render(<CompactSummaryCard body="digest" />)
    fireEvent.contextMenu(screen.getByTestId('chat-summary'))
    expect(
      screen.queryByRole('menuitem', { name: 'Include in chat context' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('menuitem', { name: '✓ Included in chat context' }),
    ).not.toBeInTheDocument()
  })
})
