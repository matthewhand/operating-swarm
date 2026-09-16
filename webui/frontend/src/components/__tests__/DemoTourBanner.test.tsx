import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DemoTourBanner } from '../DemoTourBanner'
import { TOUR_PROMPT } from '../../lib/demo/scenarios'

describe('DemoTourBanner', () => {
  it('renders scenario cards and plays the tour', () => {
    const onChoose = vi.fn()
    render(<DemoTourBanner onChoose={onChoose} />)
    expect(screen.getByTestId('demo-tour-banner')).toHaveTextContent('Operating Swarm')
    const cards = screen.getAllByTestId('demo-scenario-card')
    expect(cards.length).toBeGreaterThanOrEqual(4)
    fireEvent.click(cards[0]!)
    expect(onChoose).toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('demo-play-tour'))
    expect(onChoose).toHaveBeenCalledWith(TOUR_PROMPT)
  })

  it('does not fire while disabled', () => {
    const onChoose = vi.fn()
    render(<DemoTourBanner disabled onChoose={onChoose} />)
    fireEvent.click(screen.getByTestId('demo-play-tour'))
    expect(onChoose).not.toHaveBeenCalled()
  })
})
