/**
 * #856 slice H — the chat bottom dock is an independently testable module
 * (`features/chat/ChatBottomDock.tsx`), moved verbatim out of ChatPage.tsx.
 *
 * Pinned contract (pure move — behavior unchanged):
 *
 * 1. ChatBottomDock renders the composer form (textarea + send/stop), the
 *    connection-status banner when the socket isn't open, and the
 *    context-usage badge slot.
 * 2. Suggestion chips (demo + normal) render above the composer from the
 *    chips passed down.
 * 3. ChatPage consumes the module and no longer declares the bottom-dock
 *    JSX inline.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ChatBottomDock } from '../ChatBottomDock'

function baseProps(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    ArrowUp: (p: { className?: string }) => <span data-testid="up">{p.className}</span>,
    ChatMessageInput: () => <textarea data-testid="enhanced-input" readOnly />,
    ComposerAttachChips: () => null,
    ComposerPluginsBadge: () => null,
    ComposerSlashPopup: () => null,
    ContextUsageBadge: ({ usage }: { usage: unknown }) => (
      <span data-testid="ctx-badge">{JSON.stringify(usage)}</span>
    ),
    Layers: () => null,
    Mic: () => null,
    Paperclip: () => null,
    Plug: () => null,
    Plus: () => null,
    QueuedSendPane: () => null,
    Reply: () => null,
    Square: () => null,
    SuggestionChips: ({ chips }: { chips: string[] }) => (
      <div data-testid="chips">{chips.join(',')}</div>
    ),
    addToast: vi.fn(),
    authRejected: false,
    status: 'open',
    composerBusy: false,
    composerMenu: { plugins: { enabled: false, reason: '' } },
    composerPlaceholder: 'Message …',
    composerRef: { current: null },
    composerWrapRef: { current: null },
    chipsDisabled: false,
    chooseSuggestion: vi.fn(),
    contextUsage: { tokens: 1 },
    conversationId: 'c1',
    demoChips: [],
    filteredSlashItems: [],
    handleCompact: vi.fn(),
    handleComposerKeyDown: vi.fn(),
    handleComposerPaste: vi.fn(),
    handleInputChange: vi.fn(),
    handleMic: vi.fn(),
    handleSelectSlashItem: vi.fn(),
    handleSend: vi.fn(),
    hasSendableDraft: false,
    input: '',
    interruptRunningTurn: vi.fn(),
    isApiAgent: false,
    isSlashOpen: false,
    messages: [],
    pendingAttachments: [],
    pluginsPanelOpen: false,
    plusOpen: false,
    plusRef: { current: null },
    queued: { rows: [] },
    queuedPaneMaxHeightPx: vi.fn(() => 320),
    setQueuedHoldIds: vi.fn(),
    renderRoutingPicker: () => null,
    recentSlashIds: [],
    removeAttachment: vi.fn(),
    replyTarget: null,
    sendNowHint: false,
    setInput: vi.fn(),
    setPluginsPanelOpen: vi.fn(),
    setPlusOpen: vi.fn(),
    setReplyTarget: vi.fn(),
    setSlashSelectedIndex: vi.fn(),
    setTokenDiagOpen: vi.fn(),
    showContextUsage: false,
    showDemoChips: false,
    showSuggestionChips: false,
    slashQuery: '',
    slashSelectedIndex: 0,
    sttListening: false,
    suggestionChips: ['alpha', 'beta'],
    ...overrides,
  }
}

describe('#856 slice H — ChatBottomDock', () => {
  it('renders the composer form and submit affordance', () => {
    render(<ChatBottomDock {...baseProps({ hasSendableDraft: true }) as React.ComponentProps<typeof ChatBottomDock>} />)
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeTruthy()
    expect(screen.getByLabelText('Send')).toBeTruthy()
  })

  it('shows the offline banner only when the socket is not open', () => {
    const { unmount } = render(
      <ChatBottomDock {...baseProps({ status: 'connecting' }) as React.ComponentProps<typeof ChatBottomDock>} />,
    )
    expect(screen.getByTestId('chat-conn-status')).toBeTruthy()
    unmount()
    render(<ChatBottomDock {...baseProps({}) as React.ComponentProps<typeof ChatBottomDock>} />)
    expect(screen.queryByTestId('chat-conn-status')).toBeNull()
  })

  it('renders suggestion chips passed down and forwards choose', () => {
    render(<ChatBottomDock {...baseProps({ showSuggestionChips: true }) as React.ComponentProps<typeof ChatBottomDock>} />)
    expect(screen.getByTestId('chips')).toHaveTextContent('alpha,beta')
  })

  it('stop button replaces send state visibility when busy', () => {
    render(
      <ChatBottomDock
        {...baseProps({ composerBusy: true, hasSendableDraft: true }) as React.ComponentProps<typeof ChatBottomDock>}
      />,
    )
    expect(screen.getByTestId('composer-stop')).toBeTruthy()
    expect(screen.getByLabelText('Send')).toBeTruthy()
  })

  it('ChatPage consumes the module (no inline bottom-dock JSX)', () => {
    const fs = require('node:fs')
    const path = require('node:path')
    // eslint-disable-next-line testing-library/no-node-access -- raw source introspection, not DOM probing
    const src = fs.readFileSync(path.join(__dirname, '..', '..', '..', 'pages', 'ChatPage.tsx'), 'utf8')
    expect(src).toContain('ChatBottomDock {...chatBottomDockProps}')
    expect(src).not.toContain('os-composer-wrap')
  })
})
