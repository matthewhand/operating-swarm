/**
 * #1274 — timeline markers render as centered status chrome between messages.
 *
 * Contracts:
 * - Day markers and resumed dividers render from `ts` alone (no persistence).
 * - Status rows never carry markers.
 * - Markers are virtual: message rows keep their keys/indices, so turn-index
 *   math (edit/resend/reactions) is untouched.
 */
import { render, screen } from '@testing-library/react'
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

function baseProps(messages: any[], displayItems?: any[]) {
  return {
    // Injected components (the #856 extraction passes them down).
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
    // lib helpers (real implementations — pin behaviour, not wiring).
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
    // callbacks
    attachToolToThread: fn(),
    cacheRowSelection: fn(),
    chooseSuggestion: fn(),
    clearCliSessionHistory: fn(),
    handleBubbleContextMenu: fn(),
    handleContextToHere: fn(),
    handleSaveSummary: fn(),
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
    // state/data
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
    displayItems: displayItems ?? messages.map((message) => ({ kind: 'message', message })),
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
  } as any
}

const DAY_A = '2026-09-25T22:10:00'
const DAY_B = '2026-09-26T08:30:00'

function row(role: 'user' | 'assistant', ts: string, text: string) {
  return { key: `${role}-${ts}-${text}`, role, ts, text, streaming: false }
}

describe('#1274 timeline markers in the transcript', () => {
  it('renders a day divider where the calendar day changes', () => {
    const messages = [
      row('user', DAY_A, 'evening question'),
      row('assistant', DAY_A, 'evening answer'),
      row('user', DAY_B, 'morning question'),
    ]
    render(<ChatMessageList {...baseProps(messages)} />)
    const markers = screen.getAllByTestId('timeline-marker')
    expect(markers).toHaveLength(2)
    expect(markers[0]).toHaveAttribute('data-marker-kind', 'day')
    expect(markers[1]).toHaveAttribute('data-marker-kind', 'day')
    // Both real bubbles still render.
    expect(screen.getByText('evening question')).toBeInTheDocument()
    expect(screen.getByText('morning question')).toBeInTheDocument()
  })

  it('renders a resumed divider for a same-day gap without touching message rows', () => {
    const messages = [
      row('user', '2026-09-26T08:00:00', 'morning ping'),
      row('assistant', '2026-09-26T08:00:05', 'quick answer'),
      row('user', '2026-09-26T14:32:00', 'back again'),
    ]
    render(<ChatMessageList {...baseProps(messages)} />)
    const markers = screen.getAllByTestId('timeline-marker')
    expect(markers).toHaveLength(2)
    expect(markers[1]).toHaveAttribute('data-marker-kind', 'resumed')
    expect(markers[1].textContent).toMatch(/^Resumed \d{2}:\d{2}$/)
    // Message rows keep their identity for turn-index math.
    expect(document.querySelector('[data-message-key]')).not.toBeNull()
  })

  it('renders no markers beyond the opener within one afternoon', () => {
    const messages = [
      row('user', '2026-09-26T13:00:00', 'hi'),
      row('assistant', '2026-09-26T13:00:20', 'hello'),
    ]
    render(<ChatMessageList {...baseProps(messages)} />)
    // Only the opening day marker exists — no mid-stream dividers.
    expect(screen.getAllByTestId('timeline-marker')).toHaveLength(1)
  })
})
