/**
 * #1374 Phase B — stacked cards for a real fan-out (one row per leg).
 * A lone awaiting turn stays on the #1371 thinking row.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ChatMessageList } from '../ChatMessageList'
import type { BubbleTheme } from '../../../lib/bubbleTheme'
import type { FanOutLeg } from '../../../lib/runningCards'

vi.mock('../../../lib/api', () => ({
  configuredRemotes: () => [],
}))

const stub = (testid: string) =>
  function Stub(props: any) {
    return <div data-testid={testid}>{props?.message?.text ?? props?.children ?? null}</div>
  }

const fn = () => vi.fn(() => undefined)

function baseProps(overrides: Record<string, any> = {}) {
  const theme: BubbleTheme = 'speech'
  return {
    AgentAvatar: stub('avatar'),
    ChatMessageActions: stub('msg-actions'),
    ChatMessageBubble: function Bubble({ text }: any) {
      return <div data-testid="chat-bubble">{text}</div>
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
    agentIdFromBlueprint: (id: string) => id,
    extractThinkingBlock: () => ({}),
    formatGapLabel: (ms: number) => `${Math.round(ms / 1000)}s`,
    formatRateLimitNotice: () => 'rate limited',
    getBubbleTheme: () => ({ messageLayout: 'bubble', actionRowPlacement: 'flow' }),
    isStatusRole: () => false,
    personaForAgentMessage: () => null,
    rawOffsetForMessage: () => -1,
    themeUsesIrcGutter: () => false,
    editedAgentLabel: ({ name }: any) => name || '',
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
    agentKind: 'api',
    awaitingAssistant: false,
    blueprints: [{ id: 'codey', name: 'Codey' }],
    bubbleTheme: theme,
    chipsDisabled: false,
    cliAgents: [],
    cliRecoveryConfigTarget: null,
    composerRef: { current: null },
    configuredRemotes: () => [],
    contextMeta: { start_offset: 0 },
    contextStrategy: 'all',
    conversationId: 'c1',
    demoMode: false,
    displayItems: [],
    editingKey: null,
    expandedThinkingKeys: new Set<string>(),
    hiddenSummaryIds: [],
    hiddenMessageKeys: [],
    hydrateError: null,
    isApiAgent: true,
    isHerdrSeat: false,
    lastUserTextRef: { current: '' },
    listEndRef: { current: null },
    messages: [],
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
    workingTip: 'Thinking…',
    ...overrides,
  } as any
}

const threeLegs: FanOutLeg[] = [
  {
    id: 'alpha',
    label: 'Alpha',
    status: 'running',
    kind: 'blueprint',
    openId: 'alpha',
    batchId: 'b1',
  },
  {
    id: 'bravo',
    label: 'Bravo',
    status: 'running',
    kind: 'cli',
    openId: 'bravo',
    batchId: 'b1',
  },
  {
    id: 'hermes',
    label: 'Hermes',
    status: 'running',
    kind: 'remote',
    openId: 'hermes',
    href: 'https://hermes.example/session',
    batchId: 'b1',
  },
]

describe('#1374 fan-out Running cards', () => {
  it('keeps the #1371 thinking row when this turn launched no legs', () => {
    render(<ChatMessageList {...baseProps({ awaitingAssistant: true, fanOutLegs: [] })} />)
    expect(screen.queryByTestId('running-card-stack')).toBeNull()
    expect(screen.getByTestId('agent-row-running')).toBeInTheDocument()
  })

  it('renders N parallel rows, hover-stop, and per-id cancel', () => {
    const stopFanOutLeg = vi.fn()
    render(
      <ChatMessageList
        {...baseProps({
          awaitingAssistant: true,
          fanOutLegs: threeLegs,
          stopFanOutLeg,
        })}
      />,
    )

    expect(screen.queryByTestId('agent-row-running')).toBeNull()
    const cards = screen.getAllByTestId('running-card')
    expect(cards).toHaveLength(3)
    expect(screen.getAllByTestId('running-card-name').map((el) => el.textContent)).toEqual([
      'Alpha',
      'Bravo',
      'Hermes',
    ])

    const badges = screen.getAllByTestId('running-card-status')
    for (const badge of badges) {
      expect(badge).toHaveTextContent('Running')
      expect(badge).toHaveClass('badge-info')
      expect(badge).toHaveClass('group/badge')
    }
    expect(screen.getAllByTestId('running-card-spinner')).toHaveLength(3)

    const stops = screen.getAllByTestId('running-card-stop')
    expect(stops[0]).toHaveClass('opacity-0')
    expect(stops[0].className).toContain('group-hover/badge:opacity-100')
    expect(badges[1].contains(stops[1])).toBe(true)

    const opens = screen.getAllByTestId('running-card-open')
    expect(opens[0]).toHaveAttribute('href', '/chat?blueprint=alpha')
    expect(opens[1]).toHaveAttribute('href', '/chat?blueprint=cli_agent&mode=cli&cli=bravo')
    expect(opens[2]).toHaveAttribute('href', 'https://hermes.example/session')
    expect(opens[2]).toHaveAttribute('target', '_blank')

    fireEvent.click(stops[1])
    expect(stopFanOutLeg).toHaveBeenCalledTimes(1)
    expect(stopFanOutLeg).toHaveBeenCalledWith('bravo')
  })

  it('updates a finished row and keeps its open target', () => {
    const legs: FanOutLeg[] = [
      { ...threeLegs[0], status: 'done' },
      { ...threeLegs[1], status: 'error' },
      { ...threeLegs[2], status: 'cancelled' },
    ]
    render(<ChatMessageList {...baseProps({ fanOutLegs: legs, stopFanOutLeg: vi.fn() })} />)
    const badges = screen.getAllByTestId('running-card-status')
    expect(badges.map((el) => el.textContent?.replace('Stop', '').trim())).toEqual([
      'Done',
      'Error',
      'Cancelled',
    ])
    expect(screen.queryByTestId('running-card-stop')).toBeNull()
    expect(screen.queryByTestId('running-card-spinner')).toBeNull()
    expect(screen.getAllByTestId('running-card-open')[2]).toHaveAttribute(
      'href',
      'https://hermes.example/session',
    )
  })
})
