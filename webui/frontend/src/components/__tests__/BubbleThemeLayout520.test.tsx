import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { ChatMessageBubble } from '../ChatMessageBubble'
import { ToastProvider } from '../DaisyUI'
import { getBubbleTheme, BUBBLE_THEMES } from '../../lib/bubbleTheme'

const AVATAR = <span data-testid="avatar-child" />

function renderBubble(theme: string, avatar?: React.ReactNode) {
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
    // feed keeps its speaker label — the drop is simple-scoped
    expect(css).toMatch(
      /\[data-bubble-theme="feed"\] \.os-bubble-meta::before\s*\{[\s\S]*content:\s*attr\(data-speaker\)/,
    )
  })
})

describe('#520.3 irc — full agent name, legible floor', () => {
  it('gutter flexes to the name with a 10ch floor, 16ch cap, body-copy size', () => {
    const css = cssText()
    const block = css.match(
      /\[data-bubble-theme="irc"\] \.chat\[data-speaker\]::before\s*\{[\s\S]*?\n\}/,
    )
    expect(block).toBeTruthy()
    const rule = block![0]
    expect(rule).toContain('flex: 0 1 auto')
    expect(rule).toContain('min-width: 10ch')
    expect(rule).toContain('max-width: 16ch')
    expect(rule).toContain('font-size: 0.8125rem')
  })
})

describe('#520.4 feed — full-width cards with roomier padding', () => {
  it('cards span the column and gain padding', () => {
    const css = cssText()
    const marker = '[data-bubble-theme="feed"] .chat-start .chat-bubble,'
    const start = css.lastIndexOf(marker)
    expect(start).toBeGreaterThan(-1)
    const end = css.indexOf('\n}', start)
    const rule = css.slice(start, end)
    expect(rule).toContain('width: 100%')
    expect(rule).toContain('max-width: 100%')
    expect(rule).toContain('padding: 0.35rem 0.5rem')
  })
})
