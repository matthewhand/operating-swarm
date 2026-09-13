import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ChatMessageBubble } from '../ChatMessageBubble'
import * as clipboard from '../../lib/clipboard'

describe('REQ-117: Fenced code blocks collapse, hover expand, copy, re-collapse', () => {
  const shortCode = '```typescript\nconst a = 1\nconst b = 2\nconsole.log(a + b)\n```'
  const longCode = [
    '```typescript',
    'const line1 = 1',
    'const line2 = 2',
    'const line3 = 3',
    'const line4 = 4',
    'const line5 = 5',
    'const line6 = 6',
    'const line7 = 7',
    'const line8 = 8',
    'const line9 = 9',
    'const line10 = 10',
    'const line11 = 11',
    'const line12 = 12',
    '```',
  ].join('\n')

  let copySpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    copySpy = vi.spyOn(clipboard, 'copyTextToClipboard').mockResolvedValue('copied')
  })

  it('short code blocks (<=10 lines) are never clipped and have copy button', () => {
    const { container } = render(
      <ChatMessageBubble
        role="assistant"
        agentName="Codey"
        text={shortCode}
        streaming={false}
        canEdit={false}
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
      />,
    )

    const pre = container.querySelector('pre')
    expect(pre).toBeInTheDocument()
    expect(pre).not.toHaveClass('os-code--collapsible')
    expect(pre).not.toHaveClass('os-code--collapsed')
    expect(pre?.querySelector('[data-testid="code-expand"]')).toBeNull()
    expect(pre?.querySelector('[data-testid="code-copy"]')).toBeInTheDocument()
  })

  it('long code blocks (>10 lines) start collapsed with copy and expand buttons', () => {
    const { container } = render(
      <ChatMessageBubble
        role="assistant"
        agentName="Codey"
        text={longCode}
        streaming={false}
        canEdit={false}
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
      />,
    )

    const pre = container.querySelector('pre')
    expect(pre).toBeInTheDocument()
    expect(pre).toHaveClass('os-code--collapsible')
    expect(pre).toHaveClass('os-code--collapsed')
    expect(pre).toHaveAttribute('data-collapsed', 'true')
    expect(pre?.querySelector('[data-testid="code-copy"]')).toBeInTheDocument()

    const expandBtn = pre?.querySelector('[data-testid="code-expand"]')
    expect(expandBtn).toBeInTheDocument()
    expect(expandBtn).toHaveTextContent('Expand')
  })

  it('hovering over the collapsed block does NOT auto-expand it', () => {
    const { container } = render(
      <ChatMessageBubble
        role="assistant"
        agentName="Codey"
        text={longCode}
        streaming={false}
        canEdit={false}
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
      />,
    )

    const pre = container.querySelector('pre')!
    fireEvent.mouseEnter(pre)
    fireEvent.mouseOver(pre)

    expect(pre).toHaveClass('os-code--collapsed')
    expect(pre?.querySelector('[data-testid="code-expand"]')).toBeInTheDocument()
    expect(pre?.querySelector('[data-testid="code-collapse"]')).toBeNull()
  })

  it('clicking Expand expands the block and sticks across re-renders', () => {
    const { container, rerender } = render(
      <ChatMessageBubble
        role="assistant"
        agentName="Codey"
        text={longCode}
        streaming={false}
        canEdit={false}
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
      />,
    )

    const pre = container.querySelector('pre')!
    const expandBtn = pre.querySelector('[data-testid="code-expand"]')!
    fireEvent.click(expandBtn)

    expect(pre).not.toHaveClass('os-code--collapsed')
    expect(pre).toHaveClass('os-code--expanded')
    expect(pre).toHaveAttribute('data-expanded', 'true')

    const collapseBtn = pre.querySelector('[data-testid="code-collapse"]')
    expect(collapseBtn).toBeInTheDocument()
    expect(collapseBtn).toHaveTextContent('Collapse')

    // Rerender (scrolling/props update) -> stays expanded (sticky)
    rerender(
      <ChatMessageBubble
        role="assistant"
        agentName="Codey"
        text={longCode}
        streaming={false}
        canEdit={false}
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
      />,
    )

    const preAfterRerender = container.querySelector('pre')!
    expect(preAfterRerender).toHaveClass('os-code--expanded')
    expect(preAfterRerender?.querySelector('[data-testid="code-collapse"]')).toBeInTheDocument()
  })

  it('clicking Collapse returns the block to the collapsed state', () => {
    const { container } = render(
      <ChatMessageBubble
        role="assistant"
        agentName="Codey"
        text={longCode}
        streaming={false}
        canEdit={false}
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
      />,
    )

    const pre = container.querySelector('pre')!
    const expandBtn = pre.querySelector('[data-testid="code-expand"]')!
    fireEvent.click(expandBtn)
    expect(pre).toHaveClass('os-code--expanded')

    const collapseBtn = pre.querySelector('[data-testid="code-collapse"]')!
    fireEvent.click(collapseBtn)
    expect(pre).toHaveClass('os-code--collapsed')
    expect(pre).not.toHaveClass('os-code--expanded')
    expect(pre.querySelector('[data-testid="code-expand"]')).toBeInTheDocument()
  })

  it('copy button copies full code text even when collapsed', () => {
    const { container } = render(
      <ChatMessageBubble
        role="assistant"
        agentName="Codey"
        text={longCode}
        streaming={false}
        canEdit={false}
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
      />,
    )

    const pre = container.querySelector('pre')!
    expect(pre).toHaveClass('os-code--collapsed')
    const copyBtn = pre.querySelector('[data-testid="code-copy"]')!
    fireEvent.click(copyBtn)

    expect(copySpy).toHaveBeenCalledTimes(1)
    const copiedText = copySpy.mock.calls[0][0]
    expect(copiedText).toContain('const line1 = 1')
    expect(copiedText).toContain('const line12 = 12')
  })

  it('also collapses long code blocks in user bubbles', () => {
    const { container } = render(
      <ChatMessageBubble
        role="user"
        agentName="User"
        text={longCode}
        streaming={false}
        canEdit={false}
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
      />,
    )

    const pre = container.querySelector('pre')
    expect(pre).toHaveClass('os-code--collapsible')
    expect(pre).toHaveClass('os-code--collapsed')
    expect(pre?.querySelector('[data-testid="code-expand"]')).toBeInTheDocument()
  })
})

describe('REQ-121: Start context from here hover action', () => {
  it('shows Start context from here when strategy is cull', () => {
    const onStart = vi.fn()
    render(
      <ChatMessageBubble
        role="user"
        agentName="You"
        text="later turn"
        streaming={false}
        canEdit={false}
        canCompress={true}
        contextStrategy="cull"
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
        onCompressToHere={onStart}
      />,
    )
    const button = screen.getByRole('button', { name: 'Start context from here' })
    expect(button).toHaveAttribute('title', 'Start context from here.')
    expect(screen.getByTestId('start-context-from-here')).toBeInTheDocument()
    fireEvent.click(button)
    expect(onStart).toHaveBeenCalledTimes(1)
  })
})

describe('REQ-87: Compress to here hover action', () => {
  it('shows Compress to here on hover when canCompress is set', () => {
    const onCompress = vi.fn()
    render(
      <ChatMessageBubble
        role="user"
        agentName="You"
        text="older turn"
        streaming={false}
        canEdit={false}
        canCompress={true}
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
        onCompressToHere={onCompress}
      />,
    )
    const button = screen.getByRole('button', { name: 'Compress to here' })
    fireEvent.click(button)
    expect(onCompress).toHaveBeenCalledTimes(1)
  })
})

describe('REQ-122: No You / agent name labels above chat bubbles', () => {
  it('does not render visible You or agentName header labels above bubbles', () => {
    const { rerender } = render(
      <ChatMessageBubble
        role="user"
        agentName="Stewie"
        text="Hello world"
        streaming={false}
        canEdit={false}
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
      />,
    )

    // User bubble: no visible "You" text
    expect(screen.queryByText('You')).not.toBeInTheDocument()
    const userContainer = screen.getByLabelText('You message')
    expect(userContainer).toBeInTheDocument()

    // Assistant bubble: no visible "Stewie" text above bubble
    rerender(
      <ChatMessageBubble
        role="assistant"
        agentName="Stewie"
        text="Hello from assistant"
        streaming={false}
        canEdit={false}
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
      />,
    )

    expect(screen.queryByText('Stewie')).not.toBeInTheDocument()
    const assistantContainer = screen.getByLabelText('Stewie message')
    expect(assistantContainer).toBeInTheDocument()
  })

  it('still renders edited hint when message was edited', () => {
    render(
      <ChatMessageBubble
        role="user"
        agentName="Stewie"
        text="Edited message"
        streaming={false}
        edited={true}
        canEdit={false}
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
      />,
    )

    expect(screen.getByTestId('edited-hint')).toHaveTextContent('edited')
    expect(screen.queryByText('You')).not.toBeInTheDocument()
  })

  it('renders system preload message as a compact "Message from System" pill (REQ-207)', () => {
    render(
      <ChatMessageBubble
        role="system"
        isSystemPreload={true}
        agentName="Support"
        text="**Agents**\n- Support · support\n\n**Inference** ready."
        streaming={false}
        canEdit={false}
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
      />,
    )

    const pill = screen.getByRole('button', { name: /Message from System/i })
    expect(pill).toBeInTheDocument()
    expect(pill).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByTestId('chat-bubble')).not.toBeInTheDocument()

    fireEvent.click(pill)
    expect(pill).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByTestId('system-preload-content')).toHaveTextContent('Support · support')
  })

  it('REQ-213: right-click on the system pill opens the compacted-card menu', () => {
    render(
      <ChatMessageBubble
        role="system"
        isSystemPreload={true}
        agentName="Support"
        text="preload body"
        streaming={false}
        canEdit={false}
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
      />,
    )
    fireEvent.contextMenu(screen.getByTestId('system-preload-pill'))
    const menu = screen.getByTestId('compacted-card-context-menu')
    expect(menu).toHaveClass('menu')
    expect(screen.getByRole('menuitem', { name: 'Expand' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Copy' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Remove from view' })).toBeInTheDocument()
  })
})

describe('REQ-212 inline skill chips', () => {
  it('renders a path ref as a chip, not bare path-only text', () => {
    const onOpen = vi.fn()
    render(
      <ChatMessageBubble
        role="assistant"
        agentName="API agent"
        text="See skills/conventional-commit/SKILL.md for the contract."
        streaming={false}
        canEdit={false}
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
        skillCatalog={[
          {
            name: 'conventional-commit',
            description: 'Write a conventional commit.',
            path: 'skills/conventional-commit/SKILL.md',
            assets: [],
          },
        ]}
        onOpenSkill={onOpen}
      />,
    )
    const chip = screen.getByTestId('skill-chip')
    expect(chip).toHaveTextContent('conventional-commit')
    expect(chip).not.toHaveTextContent('skills/conventional-commit/SKILL.md')
    fireEvent.click(chip)
    expect(onOpen).toHaveBeenCalledWith('conventional-commit')
  })

  it('marks an unknown skill chip as missing', () => {
    render(
      <ChatMessageBubble
        role="user"
        agentName="You"
        text="/skill nope-not-real please"
        streaming={false}
        canEdit={false}
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
        skillCatalog={[]}
        onOpenSkill={() => {}}
      />,
    )
    expect(screen.getByTestId('skill-chip')).toHaveAttribute('data-skill-missing', 'true')
  })

  it('exposes speaker for transcript-wide bubble themes (REQ-810)', () => {
    render(
      <ChatMessageBubble
        role="assistant"
        agentName="Codey"
        text="hello"
        streaming={false}
        canEdit={false}
        editing={false}
        onStartEdit={() => {}}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
        ts="2026-09-03T06:54:00Z"
      />,
    )
    const row = screen.getByLabelText('Codey message')
    expect(row).toHaveAttribute('data-speaker', 'Codey')
    expect(row).toHaveAttribute('data-ts', '2026-09-03T06:54:00Z')
    expect(screen.getByTestId('bubble-time')).toBeInTheDocument()
  })
})


