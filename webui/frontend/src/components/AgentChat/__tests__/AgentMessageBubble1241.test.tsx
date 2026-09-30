/**
 * #1241 — idle reaction pills dim in always-visible contexts; pills the user
 * has reacted with stay full brightness.
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ToastProvider } from '../../DaisyUI'
import { AgentMessageBubble } from '../AgentMessageBubble'
import type { ChatMessage } from '../../../types/agent'

const message: ChatMessage = {
  key: 'r-1241',
  role: 'assistant',
  text: 'nice',
  timestamp: new Date(0),
  reactions: [
    { emoji: '👍', count: 1, userReacted: true },
    { emoji: '👀', count: 2, userReacted: false },
  ],
}

describe('#1241 reaction pill dimming', () => {
  it('keeps user-reacted pills bright and dims idle pills', () => {
    render(
      <ToastProvider>
        <AgentMessageBubble message={message} onAddReaction={() => {}} />
      </ToastProvider>,
    )
    const mine = screen.getByTestId('reaction-👍')
    expect(mine).toHaveAttribute('data-user-reacted', 'true')
    expect(mine.className).toContain('opacity-100')

    const idle = screen.getByTestId('reaction-👀')
    expect(idle).not.toHaveAttribute('data-user-reacted')
    expect(idle.className).toContain('opacity-45')
    expect(idle.className).toContain('hover:opacity-100')
    expect(idle.className).toContain('focus-visible:opacity-100')
    expect(idle.className).toContain('motion-reduce:transition-none')
  })
})
