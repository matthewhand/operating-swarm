import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { ReactElement } from 'react'
import { ToastProvider } from '../../DaisyUI'
import { COPY_EMPTY_TITLE, COPY_FAILED_TITLE } from '../../../lib/clipboard'
import { AgentMessageBubble } from '../AgentMessageBubble'
import type { ChatMessage } from '../../../types/agent'

function renderBubble(ui: ReactElement) {
  return render(<ToastProvider>{ui}</ToastProvider>)
}

function stubExecCommand(ok: boolean) {
  const exec = vi.fn().mockReturnValue(ok)
  Object.defineProperty(document, 'execCommand', {
    configurable: true,
    writable: true,
    value: exec,
  })
  return exec
}

const userMsg: ChatMessage = {
  key: 'u1',
  role: 'user',
  text: 'Ship a demo',
  timestamp: new Date(0),
}

const summaryMsg: ChatMessage = {
  key: 's1',
  role: 'assistant',
  text: 'We agreed to ship a demo.',
  kind: 'summary',
  compacted: [
    { role: 'user', text: 'Ship a demo' },
    { role: 'assistant', text: 'Will do' },
  ],
  timestamp: new Date(0),
}

describe('AgentMessageBubble', () => {
  beforeEach(() => {
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('reveals copy and compact actions for a chat turn', async () => {
    const onCompact = vi.fn()
    renderBubble(
      <AgentMessageBubble
        message={userMsg}
        canCompact
        onCompactToHere={onCompact}
      />,
    )
    expect(screen.getByText('Ship a demo')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Copy message' }))
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('Ship a demo')
    })
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Compact to here' }))
    expect(onCompact).toHaveBeenCalled()
  })

  it('falls back to execCommand when the Clipboard API rejects', async () => {
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
    })
    const exec = stubExecCommand(true)
    renderBubble(<AgentMessageBubble message={userMsg} />)
    fireEvent.click(screen.getByRole('button', { name: 'Copy message' }))
    await waitFor(() => {
      expect(exec).toHaveBeenCalledWith('copy')
    })
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument()
    expect(screen.queryByText(COPY_FAILED_TITLE)).not.toBeInTheDocument()
  })

  it('toasts Copy failed when clipboard and fallback both fail', async () => {
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
    })
    stubExecCommand(false)
    renderBubble(<AgentMessageBubble message={userMsg} />)
    fireEvent.click(screen.getByRole('button', { name: 'Copy message' }))
    expect(await screen.findByText(COPY_FAILED_TITLE)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Copied' })).not.toBeInTheDocument()
  })

  it('disables Copy when the message has no text', () => {
    renderBubble(
      <AgentMessageBubble
        message={{ ...userMsg, key: 'empty', text: '' }}
      />,
    )
    expect(screen.getByRole('button', { name: COPY_EMPTY_TITLE })).toBeDisabled()
  })

  it('renders a rectangular summary with regenerate and original popup', async () => {
    const onRegen = vi.fn()
    renderBubble(
      <AgentMessageBubble
        message={summaryMsg}
        onRegenerateSummary={onRegen}
      />,
    )
    expect(screen.getByText('Conversation summary')).toBeInTheDocument()
    const card = screen.getByText('We agreed to ship a demo.').parentElement
    expect(card?.className).toContain('rounded-none')

    fireEvent.click(screen.getByRole('button', { name: 'View original messages' }))
    const dialog = await screen.findByRole('dialog', { name: 'Original messages' })
    expect(dialog).toHaveTextContent('Ship a demo')
    expect(dialog).toHaveTextContent('Will do')
    fireEvent.click(screen.getByRole('button', { name: 'Close dialog' }))
    expect(screen.queryByRole('dialog', { name: 'Original messages' })).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Steer next regenerate'), {
      target: { value: 'keep API names' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Regenerate summary' }))
    expect(onRegen).toHaveBeenCalledWith('keep API names')
  })

  it('renders Python fenced blocks with pretty-print tokens', () => {
    const msg: ChatMessage = {
      key: 'py1',
      role: 'assistant',
      text: '```python\ndef greet():\n    return "hi"\n```',
      agent: 'Support',
      timestamp: new Date(0),
    }
    const { container } = renderBubble(<AgentMessageBubble message={msg} />)
    const pre = container.querySelector('pre.os-code')
    expect(pre).toBeTruthy()
    expect(pre?.className).toContain('os-code-python')
    expect(container.querySelector('.os-py-kw')).toBeTruthy()
    expect(container.querySelector('.os-py-str')).toBeTruthy()
  })

  it('does not render visible You or agent name headers above bubbles (REQ-179)', () => {
    const assistantMsg: ChatMessage = {
      key: 'a1',
      role: 'assistant',
      text: 'Here is the plan',
      agent: 'Architect',
      timestamp: new Date(0),
    }
    const { rerender } = renderBubble(<AgentMessageBubble message={assistantMsg} />)
    expect(screen.queryByText('Architect')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Architect message')).toBeInTheDocument()

    rerender(
      <ToastProvider>
        <AgentMessageBubble message={userMsg} />
      </ToastProvider>,
    )
    expect(screen.queryByText('You')).not.toBeInTheDocument()
    expect(screen.getByLabelText('You message')).toBeInTheDocument()

    const reviewMsg: ChatMessage = {
      key: 'r1',
      role: 'assistant',
      text: 'Approval needed for PR',
      kind: 'review',
      oversightRole: 'taskmaster',
      agent: 'SecurityBot',
      timestamp: new Date(0),
    }
    rerender(
      <ToastProvider>
        <AgentMessageBubble message={reviewMsg} />
      </ToastProvider>,
    )
    expect(screen.queryByText(/SecurityBot/)).not.toBeInTheDocument()
    expect(screen.getByText('Taskmaster')).toBeInTheDocument()
    expect(screen.getByLabelText('SecurityBot message')).toBeInTheDocument()
  })

  it('renders reaction row and hides on desktop until hover while staying visible on mobile (REQ-91)', () => {
    const onAddReaction = vi.fn()
    const msgWithReactions: ChatMessage = {
      key: 'r-msg',
      role: 'assistant',
      text: 'Great idea!',
      timestamp: new Date('2024-01-01T00:00:00Z'),
      reactions: [
        { emoji: '👍', count: 3, userReacted: true },
        { emoji: '🎉', count: 1, userReacted: false },
      ],
    }

    renderBubble(
      <AgentMessageBubble
        message={msgWithReactions}
        onAddReaction={onAddReaction}
      />,
    )

    const reactionRow = screen.getByTestId('message-reactions-row')
    expect(reactionRow).toBeInTheDocument()

    // Mobile: opacity-100 pointer-events-auto
    expect(reactionRow.className).toContain('opacity-100')
    expect(reactionRow.className).toContain('pointer-events-auto')

    // Desktop: concealed at rest (md:opacity-0 md:pointer-events-none), reveals on hover / focus
    expect(reactionRow.className).toContain('md:opacity-0')
    expect(reactionRow.className).toContain('md:pointer-events-none')
    expect(reactionRow.className).toContain('group-hover:md:opacity-100')
    expect(reactionRow.className).toContain('group-focus-within:md:opacity-100')

    // Action bar reaction button and visibility
    const actionsBar = screen.getByTestId('message-actions')
    expect(actionsBar.className).toContain('opacity-100')
    expect(actionsBar.className).toContain('md:opacity-0')
    expect(actionsBar.className).toContain('group-hover:md:opacity-100')

    const addReactionBtn = screen.getByRole('button', { name: 'Add reaction' })
    expect(addReactionBtn).toBeInTheDocument()
    fireEvent.click(addReactionBtn)
    expect(onAddReaction).toHaveBeenCalledWith('r-msg')

    const thumbsUpBadge = screen.getByTestId('reaction-👍')
    expect(thumbsUpBadge).toHaveTextContent('👍3')
    fireEvent.click(thumbsUpBadge)
    expect(onAddReaction).toHaveBeenCalledWith('r-msg', '👍')
  })

  it('renders system preload message as a compact "Message from System" pill without assistant avatar (REQ-207)', () => {
    const systemMsg: ChatMessage = {
      key: 'sys-preload-1',
      role: 'system',
      kind: 'system',
      isSystemPreload: true,
      text: '**Agents**\n- Support · support\n\n**Inference** ready.',
      timestamp: new Date(),
    }

    renderBubble(<AgentMessageBubble message={systemMsg} />)

    // Verify pill is rendered
    const pill = screen.getByRole('button', { name: /Message from System/i })
    expect(pill).toBeInTheDocument()
    expect(pill).toHaveAttribute('aria-expanded', 'false')

    // Verify no assistant avatar / speech bubble chrome
    expect(screen.queryByTestId('agent-avatar')).not.toBeInTheDocument()
    expect(screen.queryByTestId('message-actions')).not.toBeInTheDocument()
    expect(screen.queryByTestId('system-preload-content')).not.toBeInTheDocument()

    // Expanding reveals the preload text
    fireEvent.click(pill)
    expect(pill).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByTestId('system-preload-content')).toBeInTheDocument()
    expect(screen.getByTestId('system-preload-content')).toHaveTextContent('Support · support')
  })

  it('REQ-213: right-click on a Conversation summary opens Expand/Copy/Remove', () => {
    renderBubble(<AgentMessageBubble message={summaryMsg} />)
    fireEvent.contextMenu(screen.getByTestId('conversation-summary-card'))
    const menu = screen.getByTestId('compacted-card-context-menu')
    expect(menu).toHaveClass('menu')
    expect(screen.getByRole('menuitem', { name: 'Collapse' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Copy' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Remove from view' })).toHaveClass('text-error')
  })

  it('REQ-213: Remove from view hides the summary card without rewriting disk', () => {
    const onRemove = vi.fn()
    renderBubble(<AgentMessageBubble message={summaryMsg} onRemoveCard={onRemove} />)
    fireEvent.contextMenu(screen.getByTestId('conversation-summary-card'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Remove from view' }))
    expect(onRemove).toHaveBeenCalledTimes(1)
  })

  it('REQ-213: Message from Agent pill uses the shared System/Agent family', () => {
    renderBubble(
      <AgentMessageBubble
        message={{
          key: 'agent-pill',
          role: 'system',
          kind: 'system',
          agent: 'Codey',
          text: 'handoff from Codey',
          timestamp: new Date(),
        }}
      />,
    )
    expect(screen.getByRole('button', { name: /Message from Codey/i })).toBeInTheDocument()
  })
})



