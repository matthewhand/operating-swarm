import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import fs from 'fs'
import path from 'path'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { ChatBubbleBody, ChatMessageBubble } from '../ChatMessageBubble'
import { OPEN_SETTINGS_EVENT } from '../SettingsSheet'
import { STREAM_REPLIES_STORAGE_KEY } from '../../lib/streamReplies'
import { BUBBLE_THEME_STORAGE_KEY } from '../../lib/bubbleTheme'
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
        editing={false}
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
        editing={false}
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
        editing={false}
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
        editing={false}
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
        editing={false}
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
        editing={false}
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
        editing={false}
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
        editing={false}
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
        canCompress={true}
        contextStrategy="cull"
        editing={false}
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
        canCompress={true}
        editing={false}
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
        editing={false}
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
        editing={false}
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
        editing={false}
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
        editing={false}
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
        editing={false}
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
        editing={false}
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
        editing={false}
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
        editing={false}
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

describe('REQ-868: settings markdown links open the in-app sheet', () => {
  const bubbleProps = {
    role: 'assistant' as const,
    agentName: 'cli_agent',
    streaming: false,
    editing: false,
    onCancelEdit: () => {},
    onSaveEdit: () => {},
  }

  it('clicking Manage CLI opens Settings at cli-agents', () => {
    const opened: unknown[] = []
    const listener = (event: Event) => opened.push((event as CustomEvent).detail)
    window.addEventListener(OPEN_SETTINGS_EVENT, listener)
    render(
      <ChatMessageBubble
        {...bubbleProps}
        text="No CLI agents are configured. Configure your installed CLIs in [Manage CLI](/chat?settings=cli-agents) (Settings → CLI Agents)."
      />,
    )
    const link = screen.getByRole('link', { name: 'Manage CLI' })
    expect(link).toHaveAttribute('href', '/chat?settings=cli-agents')
    fireEvent.click(link)
    expect(opened).toEqual([{ section: 'cli-agents' }])
    window.removeEventListener(OPEN_SETTINGS_EVENT, listener)
  })

  it('settings:cli-agents protocol also opens the sheet', () => {
    const opened: unknown[] = []
    const listener = (event: Event) => opened.push((event as CustomEvent).detail)
    window.addEventListener(OPEN_SETTINGS_EVENT, listener)
    render(
      <ChatMessageBubble
        {...bubbleProps}
        text="Open [Manage CLI](settings:cli-agents)."
      />,
    )
    fireEvent.click(screen.getByRole('link', { name: 'Manage CLI' }))
    expect(opened).toEqual([{ section: 'cli-agents' }])
    window.removeEventListener(OPEN_SETTINGS_EVENT, listener)
  })

  it('ordinary markdown links do not open Settings', () => {
    const opened: unknown[] = []
    const listener = (event: Event) => opened.push((event as CustomEvent).detail)
    window.addEventListener(OPEN_SETTINGS_EVENT, listener)
    render(
      <ChatMessageBubble
        {...bubbleProps}
        text="See [docs](https://example.com/path)."
      />,
    )
    fireEvent.click(screen.getByRole('link', { name: 'docs' }))
    expect(opened).toEqual([])
    window.removeEventListener(OPEN_SETTINGS_EVENT, listener)
  })
})

describe('markdown-safe streaming (#220)', () => {
  afterEach(() => {
    localStorage.removeItem(STREAM_REPLIES_STORAGE_KEY)
    localStorage.removeItem(BUBBLE_THEME_STORAGE_KEY)
  })

  it('hides partial markdown while streaming when the user toggle is off', () => {
    const { container } = render(
      <ChatBubbleBody text="hello **wor" streaming />,
    )
    expect(container.querySelector('[data-testid="chat-md"]')).toBeNull()
    expect(container.textContent).not.toContain('**wor')
  })

  it('renders only the balanced prefix while streaming when opted in', () => {
    localStorage.setItem(STREAM_REPLIES_STORAGE_KEY, '1')
    localStorage.setItem(BUBBLE_THEME_STORAGE_KEY, 'speech')
    render(<ChatBubbleBody text="hello **wor" streaming />)
    const md = screen.getByTestId('chat-md')
    expect(md).toHaveAttribute('data-streaming-partial', 'true')
    expect(md.innerHTML.toLowerCase()).not.toContain('**')
    expect(md.textContent).toContain('hello')
    expect(md.textContent).not.toContain('wor')
    expect(screen.getByTestId('stream-affordance')).toBeInTheDocument()
  })

  it('flushes the held tail when streaming ends', () => {
    localStorage.setItem(STREAM_REPLIES_STORAGE_KEY, '1')
    render(<ChatBubbleBody text="hello **world**" streaming={false} />)
    expect(screen.getByTestId('chat-md').innerHTML).toContain('<strong>world</strong>')
  })
})

describe('#217: per-theme timestamp placement and message layout', () => {
  const ts = '2026-09-03T06:54:00Z'

  function renderThemed(
    theme: 'speech' | 'simple' | 'irc' | 'feed',
  ) {
    return render(
      <ChatMessageBubble
        theme={theme}
        role="assistant"
        agentName="Codey"
        text="hello"
        streaming={false}
        editing={false}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
        ts={ts}
      />,
    )
  }

  it('speech keeps the clock above in a bubble row', () => {
    renderThemed('speech')
    const row = screen.getByLabelText('Codey message')
    expect(row).toHaveAttribute('data-message-layout', 'bubble')
    expect(row).toHaveAttribute('data-timestamp-placement', 'above')
    const slot = screen.getByTestId('bubble-time-slot')
    expect(slot).toHaveClass('chat-header')
    expect(within(slot).getByTestId('bubble-time')).toBeInTheDocument()
  })

  it('simple puts the datetimestamp below a bubble', () => {
    renderThemed('simple')
    const row = screen.getByLabelText('Codey message')
    expect(row).toHaveAttribute('data-message-layout', 'bubble')
    expect(row).toHaveAttribute('data-timestamp-placement', 'below')
    const slot = screen.getByTestId('bubble-time-slot')
    expect(slot).toHaveClass('chat-footer')
    expect(within(slot).getByTestId('bubble-time')).toBeInTheDocument()
  })

  it('irc sits the clock inline on a full-width line', () => {
    renderThemed('irc')
    const row = screen.getByLabelText('Codey message')
    expect(row).toHaveAttribute('data-message-layout', 'line')
    expect(row).toHaveAttribute('data-timestamp-placement', 'inline')
    const slot = screen.getByTestId('bubble-time-slot')
    expect(slot).toHaveClass('os-bubble-time-inline')
    expect(within(slot).getByTestId('bubble-time')).toBeInTheDocument()
  })

  it('feed keeps the clock above on a full-width line', () => {
    renderThemed('feed')
    const row = screen.getByLabelText('Codey message')
    expect(row).toHaveAttribute('data-message-layout', 'line')
    expect(row).toHaveAttribute('data-timestamp-placement', 'above')
    const slot = screen.getByTestId('bubble-time-slot')
    expect(slot).toHaveClass('chat-header')
    expect(within(slot).getByTestId('bubble-time')).toBeInTheDocument()
  })
})

describe('REQ-867: bubble click selects text; Edit lives in MessageRowActions', () => {
  const defaultProps = {
    role: 'user' as const,
    agentName: 'You',
    text: 'Hello world to select',
    streaming: false,
    editing: false,
    onCancelEdit: () => {},
    onSaveEdit: () => {},
  }

  it('does not start edit when the bubble is clicked or double-clicked', () => {
    render(<ChatMessageBubble {...defaultProps} />)

    const bubble = screen.getByTestId('chat-bubble')
    expect(bubble).toHaveClass('select-text')
    fireEvent.click(bubble)
    fireEvent.doubleClick(bubble)

    expect(screen.queryByRole('textbox', { name: 'Edit message' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit message' })).not.toBeInTheDocument()
  })

  it('cancels on Escape and saves on Cmd+Enter while editing', () => {
    const onCancelEdit = vi.fn()
    const onSaveEdit = vi.fn()
    render(
      <ChatMessageBubble
        {...defaultProps}
        editing={true}
        onCancelEdit={onCancelEdit}
        onSaveEdit={onSaveEdit}
      />,
    )

    const textarea = screen.getByRole('textbox', { name: 'Edit message' })
    fireEvent.keyDown(textarea, { key: 'Escape' })
    expect(onCancelEdit).toHaveBeenCalledTimes(1)

    fireEvent.change(textarea, { target: { value: 'revised copy' } })
    fireEvent.keyDown(textarea, { key: 'Enter', metaKey: true })
    expect(onSaveEdit).toHaveBeenCalledWith('revised copy')
  })

  it('#521: the editor is the same bubble box, not a smaller surface', () => {
    const { unmount } = render(<ChatMessageBubble {...defaultProps} />)
    const bubble = screen.getByTestId('chat-bubble')
    const bubbleClasses = bubble.className
    expect(bubble).toHaveClass('chat-bubble', 'select-text')
    unmount()

    render(<ChatMessageBubble {...defaultProps} editing={true} />)
    const editor = screen.getByTestId('chat-bubble')
    // Same element contract as the message it replaces — so it cannot be
    // narrower — plus a flag to tell the two states apart.
    expect(editor).toHaveClass('chat-bubble', 'select-text')
    expect(editor).toHaveAttribute('data-editing', 'true')
    expect(bubbleClasses).toContain('chat-bubble')

    const textarea = screen.getByRole('textbox', { name: 'Edit message' })
    expect(textarea).toHaveClass('os-bubble-editor')
  })

  it('#521: the editor floors at the measured message height and scrolls beyond it', () => {
    const spy = vi
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockReturnValue({ height: 320 } as DOMRect)
    try {
      // Same component instance: the bubble is measured while on screen, then
      // the edit state opens against that measurement.
      const { rerender } = render(<ChatMessageBubble {...defaultProps} />)
      expect(screen.getByTestId('chat-bubble')).not.toHaveAttribute('data-editing')

      rerender(<ChatMessageBubble {...defaultProps} editing={true} />)

      const textarea = screen.getByRole('textbox', { name: 'Edit message' })
      // A long message must not produce a smaller editor than the message.
      expect((textarea as HTMLElement).style.minHeight).toBe('320px')
    } finally {
      spy.mockRestore()
    }

    const css = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf-8')
    const rule = css.slice(css.indexOf('.os-bubble-editor'))
    const body = rule.slice(0, rule.indexOf('}'))
    expect(body).toContain('overflow-y: auto')
  })
})

describe('#565 reply quote in the bubble', () => {
  const quotedProps = {
    role: 'user' as const,
    agentName: 'You',
    text: [
      '> **Support**: Existing answer text',
      '>',
      '> a second quoted line',
      '> a third quoted line',
      '> a fourth quoted line',
      '> a fifth quoted line',
      '',
      'Here is my followup',
    ].join('\n'),
    streaming: false,
    editing: false,
    onCancelEdit: () => {},
    onSaveEdit: () => {},
  }

  it('renders the leading quote separately from the reply body', () => {
    render(<ChatMessageBubble {...quotedProps} />)
    const quote = screen.getByTestId('bubble-quote')
    expect(quote).toHaveTextContent('Existing answer text')
    expect(quote).toHaveAttribute('data-clamped', 'true')
    // The reply's own text is outside the quote.
    expect(screen.getByTestId('chat-md')).toHaveTextContent('Here is my followup')
  })

  it('leaves an ordinary message with no quote untouched', () => {
    render(<ChatMessageBubble {...quotedProps} text="A plain answer" />)
    expect(screen.queryByTestId('bubble-quote')).not.toBeInTheDocument()
    expect(screen.getByTestId('chat-md')).toHaveTextContent('A plain answer')
  })

  it('does not clamp a short quote', () => {
    render(<ChatMessageBubble {...quotedProps} text={'> **Support**: just one line\n\nbody'} />)
    expect(screen.getByTestId('bubble-quote')).toHaveAttribute('data-clamped', 'false')
    expect(screen.queryByTestId('bubble-quote-toggle')).not.toBeInTheDocument()
  })
})


