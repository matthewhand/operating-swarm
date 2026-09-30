/**
 * #1319 — "Load earlier messages" affordance + scroll anchor.
 *
 * The list only renders the control and asks the parent to fetch the older
 * page; prepending that page must not jump the viewport. jsdom does not lay
 * out scroll geometry, so the anchor contract is pinned by driving
 * `scrollHeight`/`scrollTop` manually and asserting the restored offset.
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
      return <div data-testid="bubble">{text}</div>
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
    activeChatAgentId: 'codey',
    activeSelectionRef: { current: null },
    agentKind: 'cli',
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
    conversationId: 'c1',
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
    selectedAgentName: 'Codey',
    selectedBlueprint: 'codey',
    selectedTeam: null,
    showCliSessionRecovery: false,
    showSupportJourneyChips: false,
    skillCatalog: [],
    streamingMessage: null,
    summaryMap: {},
    supportJourneyChips: [],
    teamFromUrl: null,
    threadKey: 'codey',
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

describe('#1319 load earlier messages', () => {
  it('renders the control and calls back when an older page exists', () => {
    const onLoadEarlierMessages = vi.fn()
    render(
      <ChatMessageList
        {...baseProps([row(2), row(3)], {
          hasEarlierMessages: true,
          onLoadEarlierMessages,
        })}
      />,
    )
    const button = screen.getByTestId('load-earlier-messages')
    expect(button).toHaveTextContent('Load earlier messages')
    fireEvent.click(button)
    expect(onLoadEarlierMessages).toHaveBeenCalledTimes(1)
  })

  it('hides the control when there is nothing older', () => {
    render(<ChatMessageList {...baseProps([row(0), row(1)], { hasEarlierMessages: false })} />)
    expect(screen.queryByTestId('load-earlier-messages')).toBeNull()
  })

  it('disables the control while the older page is loading', () => {
    render(
      <ChatMessageList
        {...baseProps([row(2)], {
          hasEarlierMessages: true,
          loadingEarlierMessages: true,
          onLoadEarlierMessages: vi.fn(),
        })}
      />,
    )
    const button = screen.getByTestId('load-earlier-messages')
    expect(button).toBeDisabled()
    expect(button).toHaveTextContent('Loading earlier messages…')
  })

  it('anchors the scroll position when an older page is prepended', () => {
    const scrollBox = document.createElement('div')
    Object.defineProperty(scrollBox, 'scrollHeight', {
      configurable: true,
      value: 100,
    })
    scrollBox.scrollTop = 50
    const scrollBoxRef = { current: scrollBox }
    const onLoadEarlierMessages = vi.fn()

    const { rerender } = render(
      <ChatMessageList
        {...baseProps([row(2), row(3)], {
          hasEarlierMessages: true,
          onLoadEarlierMessages,
          scrollBoxRef,
        })}
      />,
    )
    fireEvent.click(screen.getByTestId('load-earlier-messages'))
    expect(onLoadEarlierMessages).toHaveBeenCalledTimes(1)

    // The parent's fetch resolves: the older page is prepended, so the
    // scrollable content grew by 200px.
    Object.defineProperty(scrollBox, 'scrollHeight', {
      configurable: true,
      value: 300,
    })
    rerender(
      <ChatMessageList
        {...baseProps([row(0), row(1), row(2), row(3)], {
          hasEarlierMessages: false,
          onLoadEarlierMessages,
          scrollBoxRef,
        })}
      />,
    )
    expect(scrollBox.scrollTop).toBe(250)
  })
})
