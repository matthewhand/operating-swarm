import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ChatMessageBubble } from '../ChatMessageBubble'
import MessageRowActions from '../MessageRowActions'
import { ToastProvider } from '../DaisyUI/Toast'

describe('Thinking block and reaction (#REQ-thinking-reaction)', () => {
  it('renders collapsible thinking block inside ChatMessageBubble when message contains thinking', () => {
    const textWithThinking = `| | summary of conversation |
| Thinking: Analyzing the codebase structure.
| Found 3 main architectural components.

Here is the answer for the user.`

    render(
      <ChatMessageBubble
        role="assistant"
        agentName="Codey"
        text={textWithThinking}
        streaming={false}
        editing={false}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
      />,
    )

    // Provider header artifact should be stripped
    expect(screen.queryByText('| | summary of conversation |')).not.toBeInTheDocument()

    // Answer should be rendered
    expect(screen.getByText('Here is the answer for the user.')).toBeInTheDocument()

    // Thinking collapsible should be rendered
    const details = screen.getByTestId('chat-thinking-block') as HTMLDetailsElement
    expect(details).toBeInTheDocument()
    expect(details.open).toBe(false)

    // Thinking text should be inside
    expect(screen.getByTestId('chat-thinking-content')).toHaveTextContent(
      /Analyzing the codebase structure/,
    )
  })

  it('renders Thinking reaction button in MessageRowActions and fires callback on click', () => {
    const onToggleThinking = vi.fn()
    render(
      <ToastProvider>
        <MessageRowActions
          text="Sample text"
          hasThinking={true}
          onToggleThinking={onToggleThinking}
          thinkingOpen={false}
        />
      </ToastProvider>,
    )

    const thinkingBtn = screen.getByTestId('message-thinking-action')
    expect(thinkingBtn).toBeInTheDocument()
    expect(thinkingBtn).toHaveAttribute('title', 'Show thinking')

    fireEvent.click(thinkingBtn)
    expect(onToggleThinking).toHaveBeenCalledTimes(1)
  })

  it('omits Thinking reaction button when hasThinking is false', () => {
    render(
      <ToastProvider>
        <MessageRowActions
          text="Sample text"
          hasThinking={false}
        />
      </ToastProvider>,
    )

    expect(screen.queryByTestId('message-thinking-action')).not.toBeInTheDocument()
  })
})
