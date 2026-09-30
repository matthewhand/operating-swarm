import { describe, it, expect } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { ChatMessageBubble } from '../ChatMessageBubble'

function renderBubble(text: string) {
  return render(
    <ChatMessageBubble
      role="assistant"
      agentName="Vision"
      text={text}
      streaming={false}
      editing={false}
      onCancelEdit={() => {}}
      onSaveEdit={() => {}}
    />,
  )
}

describe('REQ-1320: inline transcript images', () => {
  it('renders a markdown image as os-msg-image', () => {
    const { container } = renderBubble('![shot](/v1/chat/attachments/9/content)')
    const img = container.querySelector('img.os-msg-image')
    expect(img).toBeInTheDocument()
    expect(img).toHaveAttribute('src', '/v1/chat/attachments/9/content')
    expect(img).toHaveAttribute('alt', 'shot')
  })

  it('renders a bare raster data URL as an inline image', () => {
    const data = 'data:image/png;base64,iVBORw0KGgo='
    const { container } = renderBubble(`screenshot:\n\n${data}`)
    const img = container.querySelector('img.os-msg-image')
    expect(img).toBeInTheDocument()
    expect(img).toHaveAttribute('src', data)
  })

  it('opens and closes a lightbox when an image is clicked', () => {
    const { container, getByTestId, queryByTestId } = renderBubble(
      '![shot](/v1/chat/attachments/9/content)',
    )
    expect(queryByTestId('chat-image-lightbox')).toBeNull()

    const img = container.querySelector('img.os-msg-image') as HTMLImageElement
    fireEvent.click(img)
    expect(getByTestId('chat-image-lightbox')).toBeInTheDocument()
    expect(getByTestId('chat-image-lightbox-img')).toHaveAttribute('alt', 'shot')

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(queryByTestId('chat-image-lightbox')).toBeNull()
  })

  it('closes the lightbox from its close button', () => {
    const { container, getByTestId, queryByTestId } = renderBubble(
      '![shot](/v1/chat/attachments/9/content)',
    )
    fireEvent.click(container.querySelector('img.os-msg-image') as HTMLImageElement)
    fireEvent.click(getByTestId('chat-image-lightbox-close'))
    expect(queryByTestId('chat-image-lightbox')).toBeNull()
  })

  it('does not render javascript: image sources', () => {
    const { container } = renderBubble('![x](javascript:alert(1))')
    expect(container.querySelector('img.os-msg-image')).toBeNull()
    expect(container.innerHTML).not.toContain('javascript:')
  })
})
