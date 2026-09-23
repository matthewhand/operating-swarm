import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { DefaultLlmTip } from '../DefaultLlmTip'
import { DEFAULT_LLM_TIP_BODY, DEFAULT_LLM_TIP_TITLE } from '../../lib/defaultLlmTip'

describe('DefaultLlmTip', () => {
  it('renders copy, offers Settings setup, and dismisses on click', () => {
    const onDismiss = vi.fn()
    render(<DefaultLlmTip onDismiss={onDismiss} />)
    const tip = screen.getByTestId('default-llm-tip')
    expect(tip).toHaveTextContent(DEFAULT_LLM_TIP_TITLE)
    expect(tip).toHaveTextContent(DEFAULT_LLM_TIP_BODY)
    expect(screen.getByTestId('default-llm-tip-setup')).toHaveTextContent(
      'Set up in Settings',
    )
    fireEvent.click(screen.getByTestId('default-llm-tip-dismiss'))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('is an inline status banner, not a dialog', () => {
    render(<DefaultLlmTip onDismiss={() => undefined} />)
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
