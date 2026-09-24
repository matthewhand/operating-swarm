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
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ChatBottomDock } from '../ChatBottomDock'

vi.mock('../../../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../../../lib/api')>('../../../lib/api')
  return {
    ...actual,
    enhancePrompt: vi.fn(),
  }
})

import { enhancePrompt } from '../../../lib/api'
const mockEnhancePrompt = vi.mocked(enhancePrompt)

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
    composerMenu: {
      addFiles: { enabled: false, reason: '' },
      compact: { enabled: false, reason: '' },
      plugins: { enabled: false, reason: '' },
    },
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

  // #1096: the composer carries exactly ONE action — the submit. Stop moved
  // to the generating agent's transcript row (pinned in ChatMessageList and
  // ChatPage.queued tests); the dock never renders a stop, busy or not.
  it('#1096 the dock renders no stop button — submit only, busy or not', () => {
    render(
      <ChatBottomDock
        {...baseProps({ hasSendableDraft: true }) as React.ComponentProps<typeof ChatBottomDock>}
      />,
    )
    expect(screen.queryByTestId('composer-stop')).toBeNull()
    expect(screen.getByLabelText('Send')).toBeTruthy()
  })

  // #1070: the primary action is permanently mounted. Idle → disabled send
  // (greyed, not absent); queued+empty → active Send-now (same contract the
  // composer's Enter path implements via interruptRunningTurn); busy → stop.
  it('#1070 the send button is always mounted — disabled when idle', () => {
    render(<ChatBottomDock {...baseProps({}) as React.ComponentProps<typeof ChatBottomDock>} />)
    const send = screen.getByLabelText('Send') as HTMLButtonElement
    expect(send).toBeTruthy()
    expect(send.disabled).toBe(true)
    expect(send.getAttribute('aria-disabled')).toBe('true')
  })

  it('#1070 empty composer with a queued send renders the active Send-now action', () => {
    const onSendNow = vi.fn()
    render(
      <ChatBottomDock
        {...baseProps({ sendNowHint: true, onSendNow }) as React.ComponentProps<typeof ChatBottomDock>}
      />,
    )
    const sendNow = screen.getByTestId('composer-send-now') as HTMLButtonElement
    expect(sendNow).toBeTruthy()
    expect(sendNow.disabled).toBe(false)
    fireEvent.click(sendNow)
    expect(onSendNow).toHaveBeenCalledTimes(1)
  })

  it('#1070/#1096 the disabled/active send slots stay consistent while busy', () => {
    render(
      <ChatBottomDock
        {...baseProps({ composerBusy: true, hasSendableDraft: true }) as React.ComponentProps<typeof ChatBottomDock>}
      />,
    )
    expect(screen.queryByTestId('composer-stop')).toBeNull()
    expect((screen.getByLabelText('Send') as HTMLButtonElement).disabled).toBe(false)
  })

  it('ChatPage consumes the module (no inline bottom-dock JSX)', () => {
    const fs = require('node:fs')
    const path = require('node:path')
    // #856 slice M: the dock renders inside the ChatTranscriptShell — the pin
    // reads the shell for the mount and ChatPage for the absence of inline JSX.
    // eslint-disable-next-line testing-library/no-node-access -- raw source introspection, not DOM probing
    const shell = fs.readFileSync(path.join(__dirname, '..', 'ChatTranscriptShell.tsx'), 'utf8')
    expect(shell).toContain('ChatBottomDock {...chatBottomDockProps}')
    // eslint-disable-next-line testing-library/no-node-access -- raw source introspection, not DOM probing
    const src = fs.readFileSync(path.join(__dirname, '..', '..', '..', 'pages', 'ChatPage.tsx'), 'utf8')
    expect(src).not.toContain('os-composer-wrap')
  })

  describe('Prompt rewrite action in + menu (#1069)', () => {
    beforeEach(() => {
      mockEnhancePrompt.mockReset()
    })

    it('renders rewrite prompt action in + menu with disabled state when draft is empty', () => {
      render(
        <ChatBottomDock
          {...baseProps({ plusOpen: true, input: '' }) as React.ComponentProps<typeof ChatBottomDock>}
        />,
      )
      const btn = screen.getByTestId('composer-enhance-button')
      expect(btn).toBeTruthy()
      expect(btn.textContent).toContain('Rewrite prompt with AI')
      expect(btn.getAttribute('aria-disabled')).toBe('true')
    })

    it('shows info toast and closes menu when clicked with empty draft', () => {
      const addToast = vi.fn()
      const setPlusOpen = vi.fn()
      render(
        <ChatBottomDock
          {...baseProps({ plusOpen: true, input: '', addToast, setPlusOpen }) as React.ComponentProps<typeof ChatBottomDock>}
        />,
      )
      const btn = screen.getByTestId('composer-enhance-button')
      fireEvent.click(btn)
      expect(addToast).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'info',
          title: 'Rewrite prompt',
        }),
      )
      expect(setPlusOpen).toHaveBeenCalledWith(false)
    })

    it('calls enhancePrompt and updates input when clicked with draft', async () => {
      const setInput = vi.fn()
      const setPlusOpen = vi.fn()
      mockEnhancePrompt.mockResolvedValueOnce({
        prompt: 'test prompt',
        enhanced: 'Enhanced test prompt by AI',
      })
      render(
        <ChatBottomDock
          {...baseProps({
            plusOpen: true,
            input: 'test prompt',
            setInput,
            setPlusOpen,
          }) as React.ComponentProps<typeof ChatBottomDock>}
        />,
      )
      const btn = screen.getByTestId('composer-enhance-button')
      expect(btn.getAttribute('aria-disabled')).toBe('false')
      fireEvent.click(btn)

      expect(mockEnhancePrompt).toHaveBeenCalledWith('test prompt')
      expect(setPlusOpen).toHaveBeenCalledWith(false)
      await waitFor(() => {
        expect(setInput).toHaveBeenCalledWith('Enhanced test prompt by AI')
      })
    })

    it('handles failure with an error toast', async () => {
      const addToast = vi.fn()
      mockEnhancePrompt.mockRejectedValueOnce(new Error('Backend error'))
      render(
        <ChatBottomDock
          {...baseProps({
            plusOpen: true,
            input: 'failing prompt',
            addToast,
          }) as React.ComponentProps<typeof ChatBottomDock>}
        />,
      )
      const btn = screen.getByTestId('composer-enhance-button')
      fireEvent.click(btn)

      await waitFor(() => {
        expect(addToast).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'error',
            title: 'Enhance prompt',
          }),
        )
      })
    })
  })
})
