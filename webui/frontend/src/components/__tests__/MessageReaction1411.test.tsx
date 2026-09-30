import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ToastProvider } from '../DaisyUI'
import { ChatMessageBubble } from '../ChatMessageBubble'
import MessageReactionPills from '../MessageReactionPills'
import MessageRowActions from '../MessageRowActions'
import { THEME_REACTION_EMOJIS } from '../../lib/bubbleThemes/reactions'

describe('#1411 reaction picker and pills', () => {
  it('opens the palette and emits the chosen emoji', () => {
    const onAddReaction = vi.fn()
    render(
      <ToastProvider>
        <MessageRowActions text="hello" onAddReaction={onAddReaction} />
      </ToastProvider>,
    )
    fireEvent.click(screen.getByTestId('message-add-reaction'))
    expect(screen.getByTestId('message-reaction-picker')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'React with 👍' }))
    expect(onAddReaction).toHaveBeenCalledWith('👍')
  })

  it('renders pills and toggles the clicked emoji', () => {
    const onToggle = vi.fn()
    render(
      <MessageReactionPills
        reactions={[
          { emoji: '👍', count: 2, userReacted: true },
          { emoji: '👀', count: 1, userReacted: false },
        ]}
        onToggle={onToggle}
      />,
    )
    expect(screen.getByTestId('message-reactions-row')).toBeInTheDocument()
    expect(screen.getByTestId('reaction-👍')).toHaveAttribute('data-user-reacted', 'true')
    fireEvent.click(screen.getByTestId('reaction-👀'))
    expect(onToggle).toHaveBeenCalledWith('👀')
  })

  it('hides the picker when onAddReaction is omitted', () => {
    render(
      <ToastProvider>
        <MessageRowActions text="hello" />
      </ToastProvider>,
    )
    expect(screen.queryByTestId('message-add-reaction')).not.toBeInTheDocument()
  })
})

describe('#1411 theme picker and reaction-only bubble', () => {
it('picker follows the active theme set and omits the rest', () => {
    const onAddReaction = vi.fn()
    render(
      <ToastProvider>
        <MessageRowActions
          text="hello"
          onAddReaction={onAddReaction}
          reactionEmojis={THEME_REACTION_EMOJIS.irc}
        />
      </ToastProvider>,
    )
    fireEvent.click(screen.getByTestId('message-add-reaction'))
    expect(screen.getByRole('button', { name: 'React with 👀' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'React with 🚀' })).not.toBeInTheDocument()
  })

  it('renders a reaction-only turn with no text body', () => {
    render(
      <ChatMessageBubble
        role="assistant"
        agentName="Jeeves"
        text=""
        streaming={false}
        editing={false}
        reactionOnly
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
        theme="speech"
      >
        <MessageReactionPills
          alwaysVisible
          reactions={[{ emoji: '👍', count: 1, agentReacted: true }]}
        />
      </ChatMessageBubble>,
    )
    const row = screen.getByTestId('message-reactions-row')
    expect(screen.getByTestId('reaction-only-bubble')).toBeInTheDocument()
    expect(screen.getByTestId('chat-bubble')).toHaveAttribute('data-reaction-only', 'true')
    expect(screen.getByTestId('reaction-👍')).toHaveTextContent('👍')
    expect(screen.queryByText('ship it')).not.toBeInTheDocument()
    expect(row).toHaveAttribute('data-always-visible', 'true')
    expect(row.className).not.toContain('md:opacity-0')
    expect(screen.getByTestId('reaction-👍').className).not.toContain('opacity-45')
  })
})
