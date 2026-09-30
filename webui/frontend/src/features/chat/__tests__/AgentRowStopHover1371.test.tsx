/**
 * #1371 — the per-agent Stop (abort/cancel-turn) control must not be
 * permanently visible.
 *
 * The Stop button lives on the generating agent's transcript row, beside the
 * Running badge (the working avatar + spinner). It is concealed at rest and
 * revealed only while that Running badge is hovered or holds keyboard focus
 * (`group/running` + `group-hover/running` + `group-focus-within/running`).
 *
 * #1630: the reveal is implemented by `components/RunningStopBadge.tsx` —
 * hover/focus sets `data-revealed` on the badge wrapper, and `index.css`
 * reveals `.os-running-stop__abort` on `:hover`, `:focus-within` and
 * `.os-running-stop--revealed`. jsdom applies no CSS, so these tests assert
 * the real contract from both sides: the CSS rules that scope the reveal to
 * the Running badge, and the states/events jsdom can observe (absent when
 * idle, concealed at rest, revealed on hover and on focus, Tab-reachable).
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import fs from 'fs'
import path from 'path'
import { ChatMessageList } from '../ChatMessageList'
import type { BubbleTheme } from '../../../lib/bubbleTheme'

const css = fs.readFileSync(path.resolve(__dirname, '../../../index.css'), 'utf8')

vi.mock('../../lib/api', () => ({
  configuredRemotes: () => [],
}))

const stub = (testid: string) =>
  function Stub(props: any) {
    return <div data-testid={testid}>{props?.message?.text ?? props?.children ?? null}</div>
  }

const fn = () => vi.fn(() => undefined)

const STREAMING_MESSAGE = {
  key: 'assistant-streaming-1',
  role: 'assistant',
  text: 'partial answer',
  streaming: true,
  ts: '2026-09-26T08:00:00Z',
}

const DONE_MESSAGE = {
  key: 'assistant-done-1',
  role: 'assistant',
  text: 'finished answer',
  ts: '2026-09-26T08:00:00Z',
}

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
    agentKind: 'cli',
    awaitingAssistant: false,
    blueprints: [],
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
    isApiAgent: false,
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

describe('#1371 stop control is revealed only from the Running badge', () => {
  it('renders no stop control when the agent is idle', () => {
    render(
      <ChatMessageList
        {...baseProps({
          messages: [DONE_MESSAGE],
          displayItems: [{ kind: 'message', message: DONE_MESSAGE }],
        })}
      />,
    )
    expect(screen.queryByTestId('agent-row-stop')).toBeNull()
    expect(screen.queryByTestId('agent-row-running')).toBeNull()
  })

  it('conceals the stop at rest while the agent is running (awaiting first token)', () => {
    render(
      <ChatMessageList
        {...baseProps({
          awaitingAssistant: true,
          streamingMessage: null,
        })}
      />,
    )
    const stop = screen.getByTestId('agent-row-stop')
    // Concealed at rest: the badge wrapper carries no reveal state, so none of
    // the CSS reveal selectors match and the control is inert but still mounted.
    const badgeWrap = screen.getByTestId('running-status-badge')
    expect(badgeWrap).toHaveAttribute('data-revealed', 'false')
    expect(badgeWrap).not.toHaveClass('os-running-stop--revealed')
    expect(stop).toHaveAttribute('data-visible', 'false')
    // … and the stylesheet conceals it until the badge is hovered/focused.
    expect(css).toMatch(
      /\.os-running-stop__abort\s*\{[^}]*opacity:\s*0[^}]*pointer-events:\s*none/s,
    )
    expect(css).toMatch(
      /\.os-running-stop:hover \.os-running-stop__abort,\s*\.os-running-stop:focus-within \.os-running-stop__abort,\s*\.os-running-stop--revealed \.os-running-stop__abort\s*\{[^}]*opacity:\s*1[^}]*pointer-events:\s*auto/s,
    )
    // Reveal is a live interaction, not a mount-time class: hovering the badge
    // exposes the control, leaving it re-conceals it.
    fireEvent.mouseEnter(badgeWrap)
    expect(badgeWrap).toHaveAttribute('data-revealed', 'true')
    expect(badgeWrap).toHaveClass('os-running-stop--revealed')
    expect(stop).toHaveAttribute('data-visible', 'true')
    fireEvent.mouseLeave(badgeWrap)
    expect(badgeWrap).toHaveAttribute('data-revealed', 'false')
    expect(stop).toHaveAttribute('data-visible', 'false')
  })

  it('scopes the reveal to the Running badge group (hover + focus-within)', () => {
    render(
      <ChatMessageList
        {...baseProps({
          awaitingAssistant: true,
          streamingMessage: null,
        })}
      />,
    )
    const group = screen.getByTestId('agent-row-running')
    const badge = screen.getByTestId('composer-working-indicator')
    const stop = screen.getByTestId('agent-row-stop')

    // The Running badge (avatar) and its spinner live inside the reveal group.
    expect(group).toHaveClass('group/running')
    expect(group.contains(badge)).toBe(true)
    // #1684: awaiting-first-token with no tool in flight shows the eye-dots
    // only. The `.loading-spinner` this assertion used to pin belonged to the
    // badge *pill*, which is now the separate "a tool call is in flight"
    // signal — so it must be ABSENT here.
    expect(group.querySelector('.loading-spinner')).toBeNull()
    expect(screen.queryByTestId('running-badge-pill')).toBeNull()
    // The stop is inside that same group, so hovering the badge reveals it.
    expect(group.contains(stop)).toBe(true)

    const badgeWrap = screen.getByTestId('running-status-badge')
    // Reveal is bound to hovering / focus-within the Running badge group: the
    // badge wrapper is the reveal trigger, and the stylesheet gates the control
    // on that wrapper's hover, its focus-within, and its explicit reveal state.
    expect(badgeWrap).toHaveClass('os-running-stop')
    expect(css).toMatch(/\.os-running-stop:hover \.os-running-stop__abort/)
    expect(css).toMatch(/\.os-running-stop:focus-within \.os-running-stop__abort/)
    expect(css).toMatch(/\.os-running-stop--revealed \.os-running-stop__abort/)
    // Focus alone reveals it, so a keyboard user is never locked out.
    fireEvent.focus(badgeWrap)
    expect(badgeWrap).toHaveAttribute('data-revealed', 'true')
    expect(stop).toHaveAttribute('data-visible', 'true')

    // Keyboard reachable: the concealed stop still takes Tab focus.
    expect(stop).not.toBeDisabled()
    expect(stop).not.toHaveAttribute('tabindex', '-1')
  })

  it('conceals the streaming-row stop and keeps its reveal scoped to the running row', () => {
    render(
      <ChatMessageList
        {...baseProps({
          messages: [STREAMING_MESSAGE],
          displayItems: [{ kind: 'message', message: STREAMING_MESSAGE }],
        })}
      />,
    )
    const stop = screen.getByTestId('agent-row-stop')
    // Concealed at rest in the streaming row too …
    const badgeWrap = screen.getByTestId('running-status-badge')
    expect(badgeWrap).toHaveAttribute('data-revealed', 'false')
    expect(stop).toHaveAttribute('data-visible', 'false')
    expect(css).toMatch(/\.os-running-stop__abort\s*\{[^}]*opacity:\s*0/s)
    // … and only the running row's own badge group reveals it.
    fireEvent.mouseEnter(badgeWrap)
    expect(stop).toHaveAttribute('data-visible', 'true')
    fireEvent.mouseLeave(badgeWrap)
    expect(stop).toHaveAttribute('data-visible', 'false')
    expect(stop.closest('.os-running-stop')).toBe(badgeWrap)

    // The reveal group is the running message row that hosts the stop.
    const group = stop.closest('.group\\/running')
    expect(group).not.toBeNull()
  })
})
