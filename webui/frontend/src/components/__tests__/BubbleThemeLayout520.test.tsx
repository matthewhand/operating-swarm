import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { ChatMessageBubble } from '../ChatMessageBubble'
import { ToastProvider } from '../DaisyUI'
import { getBubbleTheme, BUBBLE_THEMES, type BubbleTheme } from '../../lib/bubbleTheme'

const AVATAR = <span data-testid="avatar-child" />

function renderBubble(theme: BubbleTheme, avatar?: React.ReactNode) {
  return render(
    <ToastProvider>
      <ChatMessageBubble
        theme={theme}
        role="assistant"
        agentName="Agy"
        text="hello"
        ts="2026-09-19T00:00:00Z"
        streaming={false}
        editing={false}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
        avatar={avatar}
      />
    </ToastProvider>,
  )
}

function cssText(): string {
  return fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf-8')
}

describe('#520 theme contract: showAvatar', () => {
  it('simple opts out; every other theme keeps the beside-bubble avatar', () => {
    for (const id of BUBBLE_THEMES) {
      expect(getBubbleTheme(id).showAvatar, `theme ${id}`).toBe(id !== 'simple')
    }
  })

  it('describe() publishes showAvatar for every theme', () => {
    for (const id of BUBBLE_THEMES) {
      expect(getBubbleTheme(id).describe().showAvatar).toBe(getBubbleTheme(id).showAvatar)
    }
  })
})

describe('#520.1 speech — avatar anchors to the bubble', () => {
  it('renders the avatar with the bottom-anchor attribute', () => {
    renderBubble('speech', AVATAR)
    const avatar = screen.getByTestId('chat-avatar')
    expect(avatar).toHaveAttribute('data-avatar-anchor', 'bottom')
  })

  it('CSS pins the bottom alignment for the speech theme only', () => {
    const css = cssText()
    expect(css).toMatch(
      /\[data-bubble-theme="speech"\] \.chat-start:has\(\.chat-image\) \.chat-image\s*\{[\s\S]*align-self:\s*flex-end/,
    )
  })
})

describe('#520.2 simple — no avatar, no speaker label', () => {
  it('does not render the beside-bubble avatar even when one is offered', () => {
    renderBubble('simple', AVATAR)
    expect(screen.queryByTestId('chat-avatar')).not.toBeInTheDocument()
    // the avatar child is simply not mounted
    expect(screen.queryByTestId('avatar-child')).not.toBeInTheDocument()
  })

  it('keeps the timestamp (below placement) and drops the speaker prefix in CSS', () => {
    renderBubble('simple')
    expect(screen.getAllByTestId('bubble-time-slot').length).toBeGreaterThan(0)
    const css = cssText()
    expect(css).toMatch(
      /\[data-bubble-theme="simple"\] \.chat\[data-speaker\]::before\s*\{[\s\S]*content:\s*none/,
    )
    expect(css).toMatch(
      /\[data-bubble-theme="simple"\] \.os-bubble-meta::before\s*\{[\s\S]*content:\s*none/,
    )
  })
})

describe('#520.3 irc — full agent name, legible floor', () => {
  it('#675: gutter is a fixed resizable width, body-copy size kept', () => {
    const css = cssText()
    const block = css.match(
      /\[data-bubble-theme="irc"\] \.chat\[data-speaker\]::before\s*\{[\s\S]*?\n\}/,
    )
    expect(block).toBeTruthy()
    const rule = block![0]
    // #675 superseded the flex/min/max ch sizing: the width is the persisted,
    // divider-dragged --irc-gutter-px so all bodies align on one vertical edge.
    expect(rule).toContain('flex: 0 0 var(--irc-gutter-px)')
    expect(rule).toContain('width: var(--irc-gutter-px)')
    expect(rule).toContain('font-size: 0.8125rem')
  })
})

describe('#520.4 retired — feed theme removed by #808', () => {
  it('no feed theme rules remain in the stylesheet', () => {
    expect(cssText()).not.toMatch(/\[data-bubble-theme="feed"\]/)
  })
})
