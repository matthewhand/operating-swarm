import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { ChatMessageBubble } from '../ChatMessageBubble'
import { voiceNoteMarkdown } from '../../lib/voiceNotes'

function renderBubble(text: string) {
  return render(
    <ChatMessageBubble
      role="user"
      agentName="You"
      text={text}
      streaming={false}
      editing={false}
      onCancelEdit={() => {}}
      onSaveEdit={() => {}}
    />,
  )
}

describe('#1322: voice notes as audio bubbles', () => {
  it('renders Voice note markdown as os-msg-audio', () => {
    const { container } = renderBubble(
      voiceNoteMarkdown('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'),
    )
    const audio = container.querySelector('audio.os-msg-audio')
    expect(audio).toBeInTheDocument()
    expect(audio).toHaveAttribute(
      'src',
      '/v1/chat/attachments/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/content?media=audio',
    )
    expect(container.querySelectorAll('audio.os-msg-audio')).toHaveLength(1)
    expect(audio).toHaveAttribute('controls')
    expect(audio).not.toHaveAttribute('autoplay')
    expect(container.querySelector('img.os-msg-image')).toBeNull()
  })

  it('renders a media=audio attachment URL even when the alt is not Voice note', () => {
    const { container } = renderBubble(
      '![shot](/v1/chat/attachments/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/content?media=audio)',
    )
    const players = container.querySelectorAll('audio.os-msg-audio')
    expect(players).toHaveLength(1)
    expect(players[0]).toHaveAttribute('controls')
    expect(players[0]).toHaveAttribute(
      'src',
      '/v1/chat/attachments/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/content?media=audio',
    )
    expect(container.querySelector('img.os-msg-image')).toBeNull()
  })

  it('keeps a generic attachment URL as an image', () => {
    const { container } = renderBubble('![shot](/v1/chat/attachments/9/content)')
    expect(container.querySelector('audio.os-msg-audio')).toBeNull()
    expect(container.querySelector('img.os-msg-image')).toBeInTheDocument()
  })

  it('renders an audio file href as an audio bubble', () => {
    const { container } = renderBubble('![clip](/media/note.webm)')
    const audio = container.querySelector('audio.os-msg-audio')
    expect(audio).toBeInTheDocument()
    expect(audio).toHaveAttribute('src', '/media/note.webm')
  })

  it('does not render javascript: audio sources', () => {
    const { container } = renderBubble('![Voice note](javascript:alert(1))')
    expect(container.querySelector('audio.os-msg-audio')).toBeNull()
    expect(container.innerHTML).not.toContain('javascript:')
  })
})
