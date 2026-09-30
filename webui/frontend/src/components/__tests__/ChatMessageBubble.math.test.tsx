import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { ChatMessageBubble } from '../ChatMessageBubble'

function renderBubble(text: string) {
  return render(
    <ChatMessageBubble
      role="assistant"
      agentName="Math"
      text={text}
      streaming={false}
      editing={false}
      onCancelEdit={() => {}}
      onSaveEdit={() => {}}
    />,
  )
}

describe('REQ-1321: LaTeX in the transcript', () => {
  it('renders inline and display math inside the bubble', () => {
    const { container } = renderBubble('Inline $E=mc^2$.\n\n$$\\int_0^1 x\\,dx$$')
    expect(container.querySelector('.katex')).toBeInTheDocument()
    expect(container.querySelector('.katex-display')).toBeInTheDocument()
    expect(container.textContent).not.toContain('$E=mc^2$')
  })

  it('renders malformed math as an inline error rather than crashing', () => {
    const { container } = renderBubble('$\\frac{1}{$')
    expect(container.querySelector('.katex-error')).toBeInTheDocument()
  })

  it('keeps $ literal inside a code span', () => {
    const { container } = renderBubble('use `$x$` here')
    expect(container.querySelector('.katex')).toBeNull()
    expect(container.textContent).toContain('$x$')
  })
})
