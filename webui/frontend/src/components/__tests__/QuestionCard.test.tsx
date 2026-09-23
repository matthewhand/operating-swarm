import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { QuestionCard } from '../QuestionCard'

const QUESTION = {
  id: 'deploy-profile',
  ask: 'Which profile should I deploy?',
  choices: ['staging', 'canary', 'prod'],
  other: 'Custom profile',
}

describe('QuestionCard', () => {
  it('renders radio choices plus a custom last option', () => {
    const onChoose = vi.fn()
    render(<QuestionCard question={QUESTION} onChoose={onChoose} />)
    const card = screen.getByTestId('question-card')
    expect(card).toHaveAttribute('data-question-id', 'deploy-profile')
    expect(card).toHaveAttribute('role', 'radiogroup')
    fireEvent.click(screen.getByRole('radio', { name: 'canary' }))
    expect(onChoose).toHaveBeenCalledWith('canary')
  })

  it('sends custom free-text as the answer', () => {
    const onChoose = vi.fn()
    render(<QuestionCard question={QUESTION} onChoose={onChoose} />)
    fireEvent.change(screen.getByLabelText('Custom profile'), {
      target: { value: 'eu-west' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(onChoose).toHaveBeenCalledWith('eu-west')
  })

  it('disables choices after the operator answers', () => {
    render(<QuestionCard question={QUESTION} disabled onChoose={vi.fn()} />)
    expect(screen.getByRole('radio', { name: 'staging' })).toBeDisabled()
    expect(screen.getByLabelText('Custom profile')).toBeDisabled()
  })
})
