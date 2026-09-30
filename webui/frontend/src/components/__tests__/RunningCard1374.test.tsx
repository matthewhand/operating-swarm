/**
 * #1374 Phase B — Cursor-like Running card: badge, hover-stop, open arrow.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ReactElement } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { RunningCard } from '../RunningCard'
import { RUNNING_CARD_STOP_CLASS } from '../../lib/runningCards'

function renderCard(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('RunningCard (#1374)', () => {
  it('shows a blue Running badge with a spinner and a concealed stop', () => {
    const onStop = vi.fn()
    renderCard(
      <RunningCard
        legId="alpha"
        name="Alpha"
        badge="Running"
        status="running"
        live
        href="/chat?blueprint=alpha"
        onStop={onStop}
      />,
    )

    const badge = screen.getByTestId('running-card-status')
    expect(badge).toHaveClass('badge-info')
    expect(badge).toHaveClass('group/badge')
    expect(badge).toHaveTextContent('Running')
    expect(screen.getByTestId('running-card-spinner')).toBeInTheDocument()

    const stop = screen.getByTestId('running-card-stop')
    expect(badge.contains(stop)).toBe(true)
    expect(stop).toHaveClass('opacity-0')
    expect(stop).toHaveClass('pointer-events-none')
    expect(stop.className).toContain('group-hover/badge:opacity-100')
    expect(stop.className).toBe(RUNNING_CARD_STOP_CLASS)
    expect(screen.getByTestId('running-card')).not.toHaveClass('group/running')

    const open = screen.getByTestId('running-card-open')
    expect(open).toHaveAttribute('href', '/chat?blueprint=alpha')
    expect(open).not.toHaveAttribute('target')
  })

  it('stop calls cancel for this leg id only', () => {
    const onStop = vi.fn()
    renderCard(
      <RunningCard
        legId="bravo"
        name="Bravo"
        badge="Running"
        status="running"
        live
        href="/chat?blueprint=bravo"
        onStop={onStop}
      />,
    )
    fireEvent.click(screen.getByTestId('running-card-stop'))
    expect(onStop).toHaveBeenCalledTimes(1)
    expect(onStop).toHaveBeenCalledWith('bravo')
  })

  it('updates the badge when done and keeps the open control', () => {
    render(
      <RunningCard
        legId="alpha"
        name="Alpha"
        badge="Done"
        status="done"
        href="/chat?blueprint=alpha"
        onStop={() => undefined}
      />,
    )
    expect(screen.getByTestId('running-card-status')).toHaveTextContent('Done')
    expect(screen.queryByTestId('running-card-stop')).toBeNull()
    expect(screen.queryByTestId('running-card-spinner')).toBeNull()
    expect(screen.getByTestId('running-card-open')).toHaveAttribute('href', '/chat?blueprint=alpha')
  })

  it('opens a remote leg in a new tab', () => {
    render(
      <RunningCard
        legId="hermes"
        name="Hermes"
        badge="Running"
        status="running"
        live
        href="https://hermes.example/ui"
        external
      />,
    )
    const open = screen.getByTestId('running-card-open')
    expect(open).toHaveAttribute('href', 'https://hermes.example/ui')
    expect(open).toHaveAttribute('target', '_blank')
    expect(open).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('omits the open control when a finished remote has no destination', () => {
    render(
      <RunningCard legId="hermes" name="Hermes" badge="Error" status="error" />,
    )
    expect(screen.queryByTestId('running-card-open')).toBeNull()
    expect(screen.getByTestId('running-card-status')).toHaveTextContent('Error')
  })
})
