/**
 * #1793 — the transcript must never read as "your messages are gone".
 *
 * The render, not the request, is where the false impression was created:
 * between mount and hydrate resolution the list rendered `null` (literally
 * nothing), and a silent miss rendered the same "Message <seat>" empty state a
 * genuinely new conversation gets. Both now have their own phase.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ChatMessageList } from '../ChatMessageList'
import { isStatusRole } from '../../../lib/chatStatus'
import { getBubbleTheme } from '../../../lib/bubbleTheme'
import { rawOffsetForMessage } from '../../../lib/chatCompact'
import { extractThinkingBlock } from '../../../lib/messageArtifacts'
import { agentIdFromBlueprint } from '../../../lib/agentChat'

vi.mock('../../lib/api', () => ({
  configuredRemotes: () => [],
}))

const stub = (testid: string) =>
  function Stub(props: any) {
    return <div data-testid={testid}>{props?.message?.text ?? props?.children ?? null}</div>
  }

const fn = () => vi.fn(() => undefined)

function baseProps(messages: any[], overrides: Record<string, any> = {}) {
  return {
    AgentAvatar: stub('avatar'),
    ChatMessageActions: stub('msg-actions'),
    ChatMessageBubble: function Bubble({ text }: any) {
      return (
        <div data-testid="bubble">
          {text}
          <button type="button" data-testid="bubble-reaction">
            react
          </button>
        </div>
      )
    },
    ChatNewRule: stub('new-rule'),
    CliSessionRecoveryBanner: stub('recovery'),
    DemoTourBanner: stub('tour'),
    IrcNoticeLine: stub('irc-notice'),
    MessageRowActions: stub('row-actions'),
    PrOpenedCard: stub('pr-card'),
    QuestionCard: stub('question'),
    RateLimitStatusLine: stub('rate-limit'),
    ReadAloudButton: stub('read-aloud'),
    SuggestionChips: stub('chips'),
    SummaryBlock: stub('summary-block'),
    SystemPreloadPill: stub('preload'),
    TeammateTaskCard: stub('teammate'),
    ToolCallPopup: stub('tool-popup'),
    SubagentFanOutBlock: stub('fanout'),
    SHOW_MESSAGE_ACTIONS: false,
    START_CONTEXT_FROM_HERE_LABEL: 'Context from here',
    agentIdFromBlueprint,
    extractThinkingBlock,
    getBubbleTheme,
    isStatusRole,
    personaForAgentMessage: () => null,
    rawOffsetForMessage,
    themeUsesIrcGutter: () => false,
    editedAgentLabel: ({ name }: any) => name || '',
    formatGapLabel: (ms: number) => `${Math.round(ms / 1000)}s`,
    formatRateLimitNotice: () => 'rate limited',
    settingsTargetForProvider: () => ({ section: 'llm', providerId: '' }),
    resolveReplyQuote: () => null,
    parseCreatedAtMs: (ts?: string) => (ts ? new Date(ts).getTime() : null),
    attachToolToThread: fn(),
    cacheRowSelection: fn(),
    chooseSuggestion: fn(),
    clearCliSessionHistory: fn(),
    handleBubbleContextMenu: fn(),
    handleContextToHere: fn(),
    handleSaveSummary: fn(),
    handleToggleSummaryContext: fn(),
    onResendSend: fn(),
    jumpToPrOpener: fn(),
    openSettingsSheet: fn(),
    rememberAlwaysAllow: fn(),
    retryCliSession: fn(),
    saveEditedMessage: fn(),
    sendQuestionAnswer: fn(),
    sendText: fn(),
    sendToolDecision: fn(),
    setEditingKey: fn(),
    setHiddenMessageKeys: fn(),
    setHiddenSummaryIds: fn(),
    setOpenSkillName: fn(),
    setRawResponseModalText: fn(),
    setReplyTarget: fn(),
    setThreads: fn(),
    startFreshCliSession: fn(),
    toggleThinking: fn(),
    interruptRunningTurn: fn(),
    activeChatAgentId: 'remote:trueforge-2',
    activeSelectionRef: { current: null },
    agentKind: 'remote',
    awaitingAssistant: false,
    blueprints: [],
    bubbleTheme: 'simple',
    chipsDisabled: false,
    cliAgents: [],
    cliRecoveryConfigTarget: null,
    composerRef: { current: null },
    configuredRemotes: () => [],
    contextMeta: { start_offset: 0 },
    contextStrategy: 'all',
    conversationId: 'remote-trueforge-2',
    demoMode: false,
    displayItems: messages.map((message) => ({ kind: 'message', message })),
    editingKey: null,
    expandedThinkingKeys: new Set<string>(),
    hiddenSummaryIds: [],
    hiddenMessageKeys: [],
    hydrateError: null,
    isApiAgent: false,
    isHerdrSeat: false,
    lastUserTextRef: { current: '' },
    listEndRef: { current: null },
    messages,
    messagesEditable: false,
    newBeforeKey: null,
    nowMs: Date.now(),
    remotesListQuery: { data: [] },
    restoreNotice: null,
    selectedAgent: null,
    selectedAgentName: 'TrueForge',
    selectedBlueprint: '',
    selectedTeam: null,
    showCliSessionRecovery: false,
    showSupportJourneyChips: false,
    skillCatalog: [],
    streamingMessage: null,
    summaryMap: {},
    supportJourneyChips: [],
    teamFromUrl: null,
    threadKey: 'remote-trueforge-2',
    threadReady: true,
    voiceBind: null,
    workingTip: null,
    ...overrides,
  } as any
}

const row = (i: number) => ({
  key: `m${i}`,
  role: i % 2 === 0 ? 'user' : 'assistant',
  text: `message ${i}`,
  streaming: false,
})

describe('#1793 loading with a cached copy on screen', () => {
  it('renders the cached copy dimmed and inert, with a live status region', () => {
    render(
      <ChatMessageList {...baseProps([row(0), row(1)], { threadReady: false })} />,
    )

    // The rows are still on screen — an empty transcript here is exactly the
    // "your messages are gone" impression this replaces.
    expect(screen.getByText('message 0')).toBeInTheDocument()
    expect(screen.getByText('message 1')).toBeInTheDocument()

    const firstRow = document.querySelector('[data-message-key="m0"]') as HTMLElement
    expect(firstRow).toBeTruthy()
    // Dimmed by the theme-token class…
    expect(firstRow).toHaveClass('os-thread-stale')
    // …announced as not-final…
    expect(firstRow).toHaveAttribute('aria-busy', 'true')
    // …and non-interactive, so no control inside it is clickable-but-confused.
    expect(firstRow).toHaveAttribute('inert')
    expect(firstRow).toHaveAttribute('data-stale-copy', 'true')
  })

  it('announces the loading state in a live region outside the stale rows', () => {
    render(<ChatMessageList {...baseProps([row(0)], { threadReady: false })} />)
    const status = screen.getByTestId('chat-thread-stale-status')
    expect(status).toHaveAttribute('role', 'status')
    expect(status).toHaveAttribute('aria-live', 'polite')
    expect(status).toHaveTextContent(/previous copy/i)
    // The live region must NOT sit inside an aria-busy subtree, or AT defers
    // the very sentence the operator needs to hear.
    expect(status.closest('[aria-busy="true"]')).toBeNull()
    expect(screen.getByTestId('chat-messages-container')).toHaveAttribute(
      'data-load-phase',
      'loading-stale',
    )
  })

  it('disables the "Load earlier messages" control while the copy is stale', () => {
    const onLoadEarlierMessages = vi.fn()
    render(
      <ChatMessageList
        {...baseProps([row(0)], {
          threadReady: false,
          hasEarlierMessages: true,
          onLoadEarlierMessages,
        })}
      />,
    )
    const button = screen.getByTestId('load-earlier-messages')
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
    fireEvent.click(button)
    expect(onLoadEarlierMessages).not.toHaveBeenCalled()
  })

  it('drops the stale marking and re-enables the control once the load settles', () => {
    const onLoadEarlierMessages = vi.fn()
    const { rerender } = render(
      <ChatMessageList
        {...baseProps([row(0)], {
          threadReady: false,
          hasEarlierMessages: true,
          onLoadEarlierMessages,
        })}
      />,
    )
    expect(screen.getByTestId('load-earlier-messages')).toBeDisabled()
    expect(screen.getByTestId('chat-thread-stale-status')).toBeInTheDocument()

    rerender(
      <ChatMessageList
        {...baseProps([row(0)], {
          threadReady: true,
          hasEarlierMessages: true,
          onLoadEarlierMessages,
        })}
      />,
    )
    const row0 = document.querySelector('[data-message-key="m0"]') as HTMLElement
    expect(row0).not.toHaveClass('os-thread-stale')
    expect(row0).not.toHaveAttribute('inert')
    const button = screen.getByTestId('load-earlier-messages')
    expect(button).not.toBeDisabled()
    expect(screen.queryByTestId('chat-thread-stale-status')).not.toBeInTheDocument()
    fireEvent.click(button)
    expect(onLoadEarlierMessages).toHaveBeenCalledTimes(1)
  })

  it('keeps the row DOM identity stable across the stale -> ready flip', () => {
    // A wrapper that appears and disappears with the phase would unmount and
    // remount every row, dropping focus, selection and scroll anchoring.
    const { rerender } = render(
      <ChatMessageList {...baseProps([row(0), row(1)], { threadReady: false })} />,
    )
    const before = document.querySelector('[data-message-key="m0"]')
    rerender(<ChatMessageList {...baseProps([row(0), row(1)], { threadReady: true })} />)
    const after = document.querySelector('[data-message-key="m0"]')
    expect(after).toBe(before)
  })
})

describe('#1793 loading with no cached copy', () => {
  it('renders a loading state, not an empty thread', () => {
    render(<ChatMessageList {...baseProps([], { threadReady: false })} />)
    const loading = screen.getByTestId('chat-thread-loading')
    expect(loading).toHaveAttribute('role', 'status')
    expect(loading).toHaveAttribute('aria-live', 'polite')
    expect(loading).toHaveTextContent(/Loading this conversation/i)
    // The empty-thread state is the false "your messages are gone" surface.
    expect(screen.queryByText('Message TrueForge')).not.toBeInTheDocument()
    expect(screen.queryByTestId('chat-hydrate-error')).not.toBeInTheDocument()
    expect(screen.getByTestId('chat-messages-container')).toHaveAttribute(
      'data-load-phase',
      'loading-empty',
    )
  })
})

describe('#1793 a failed load is never an empty thread', () => {
  it('renders the explicit error state on an empty transcript', () => {
    render(
      <ChatMessageList
        {...baseProps([], { threadReady: true, hydrateError: 'thread store unavailable' })}
      />,
    )
    const error = screen.getByTestId('chat-hydrate-error')
    expect(error).toHaveAttribute('role', 'alert')
    expect(error).toHaveTextContent('Could not load this chat')
    expect(error).toHaveTextContent('thread store unavailable')
    expect(screen.queryByText('Message TrueForge')).not.toBeInTheDocument()
  })

  it('says so even when a previous copy is still on screen', () => {
    render(
      <ChatMessageList
        {...baseProps([row(0), row(1)], { threadReady: true, hydrateError: 'upstream 500' })}
      />,
    )
    // The copy is kept…
    expect(screen.getByText('message 0')).toBeInTheDocument()
    // …but it is labelled as the kept copy, not as live data.
    const notice = screen.getByTestId('chat-thread-stale-error')
    expect(notice).toHaveAttribute('role', 'alert')
    expect(notice).toHaveTextContent(/could not refresh/i)
    expect(notice).toHaveTextContent('upstream 500')
    const row0 = document.querySelector('[data-message-key="m0"]') as HTMLElement
    expect(row0).not.toHaveClass('os-thread-stale')
  })
})

describe('#1793 a genuinely empty conversation is still an empty thread', () => {
  it('shows the new-conversation state once the load settles with no rows', () => {
    render(<ChatMessageList {...baseProps([], { threadReady: true, hydrateError: null })} />)
    expect(screen.getByText('Message TrueForge')).toBeInTheDocument()
    expect(screen.queryByTestId('chat-thread-loading')).not.toBeInTheDocument()
    expect(screen.queryByTestId('chat-hydrate-error')).not.toBeInTheDocument()
  })
})
