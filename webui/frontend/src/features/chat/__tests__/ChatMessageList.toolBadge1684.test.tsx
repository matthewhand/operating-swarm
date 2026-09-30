/**
 * #1684 — the two working-state indicators are DIFFERENT states.
 *
 * Before: one flag (`isStreamingAssistant`) drove both the avatar's eye-dots
 * and the "Running" badge, so a plain streaming turn showed a triple-bounce
 * spinner AND a badge — two identical-looking views of one boolean
 * (`docs/UI_DESIGN.md` §3, "Never drive both from one flag").
 *
 * After:
 *   • eye-dots  = "waiting on a model response"  → `isStreamingAssistant`
 *   • Running   = "a tool call is in flight"     → `useActiveToolForAgent`,
 *     i.e. the live `tool_status` frames the server already emits
 *     (`core/turn_phase.py`), folded into the SPA turn registry.
 *
 * These tests drive the rows through `ChatMessageList` directly with the real
 * registry, so no server and no `ChatPage` is needed.
 */
import { render, screen, fireEvent, act } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatMessageList } from '../ChatMessageList'
import {
  recordToolPhaseFrame,
  recordTurnFrame,
  resetTurnRegistry,
  type ToolPhaseFrame,
} from '../../../lib/agentTurns'
import type { BubbleTheme } from '../../../lib/bubbleTheme'

vi.mock('../../lib/api', () => ({ configuredRemotes: () => [] }))

const stub = (testid: string) =>
  function Stub() {
    return <div data-testid={testid} />
  }

const fn = () => vi.fn(() => undefined)

/** The exact wire shape of a live `tool_status` frame: no `turn_id`. */
const toolFrame = (
  id: string,
  name: string,
  status: string,
  agentId: string,
): ToolPhaseFrame => ({ kind: 'tool_status', id, name, status, agentId })

const STREAMING_MESSAGE = {
  key: 'assistant-streaming-1',
  role: 'assistant',
  text: 'partial answer',
  streaming: true,
  ts: '2026-09-26T08:00:00Z',
}

function baseProps(overrides: Record<string, any> = {}) {
  const theme: BubbleTheme = 'speech'
  return {
    AgentAvatar: stub('avatar'),
    ChatMessageActions: stub('msg-actions'),
    ChatMessageBubble: function Bubble({ children, avatar }: any) {
      return (
        <div data-testid="chat-bubble">
          {avatar}
          {children}
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
    SubagentFanOutBlock: stub('fanout'),
    SuggestionChips: stub('chips'),
    SummaryBlock: stub('summary-block'),
    SystemPreloadPill: stub('preload'),
    TeammateTaskCard: stub('teammate'),
    ToolCallPopup: stub('tool-popup'),
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

const streamingProps = (overrides: Record<string, any> = {}) =>
  baseProps({
    messages: [STREAMING_MESSAGE],
    displayItems: [{ kind: 'message', message: STREAMING_MESSAGE }],
    ...overrides,
  })

/**
 * Only a `beforeEach` reset: vitest runs `afterEach` hooks in reverse
 * registration order, so a reset here would fire *before* RTL's auto-cleanup
 * and notify a still-mounted component outside `act`. The registry is
 * process-global and fully replaced by the next `beforeEach` anyway.
 */
beforeEach(() => {
  resetTurnRegistry()
})

describe('#1684: plain streaming shows the eye-dots and NO badge', () => {
  it('the streaming row badged off `streaming` before — now it badges off the tool phase', () => {
    render(<ChatMessageList {...streamingProps()} />)

    // Indicator (a): the avatar's working mark is unchanged.
    expect(screen.getByTestId('composer-working-indicator')).toBeTruthy()
    // Indicator (b): no tool is in flight, so there is no Running badge. The
    // two are no longer two views of one boolean.
    expect(screen.queryByTestId('running-badge-pill')).toBeNull()
    // The stop control is still mounted and still hover-revealed — the fix is
    // the badge's signal, not a loss of the interrupt affordance.
    expect(screen.getByTestId('agent-row-stop')).toHaveAttribute('data-visible', 'false')
  })

  it('badges, naming the tool, as soon as a tool_status frame says a tool is running', () => {
    recordTurnFrame({ kind: 'turn_started', turnId: 't1', agentId: 'codey' })
    render(<ChatMessageList {...streamingProps()} />)
    expect(screen.queryByTestId('running-badge-pill')).toBeNull()

    act(() => {
      recordToolPhaseFrame(toolFrame('c1', 'read_file', 'running', 'codey'))
    })
    const pill = screen.getByTestId('running-badge-pill')
    expect(pill).toHaveTextContent('Running · read_file')
  })

  it('clears the badge on the tool terminal frame, leaving the eye-dots alone', () => {
    recordTurnFrame({ kind: 'turn_started', turnId: 't1', agentId: 'codey' })
    recordToolPhaseFrame(toolFrame('c1', 'read_file', 'running', 'codey'))
    render(<ChatMessageList {...streamingProps()} />)
    expect(screen.getByTestId('running-badge-pill')).toBeTruthy()

    act(() => {
      recordToolPhaseFrame(toolFrame('c1', 'read_file', 'done', 'codey'))
    })
    expect(screen.queryByTestId('running-badge-pill')).toBeNull()
    // The row is still streaming: "waiting on a model response" is unchanged.
    expect(screen.getByTestId('composer-working-indicator')).toBeTruthy()
    expect(screen.getByTestId('agent-row-stop')).toBeTruthy()
  })

  it('never badges a tool belonging to a different agent', () => {
    recordTurnFrame({ kind: 'turn_started', turnId: 't1', agentId: 'codey' })
    recordTurnFrame({ kind: 'turn_started', turnId: 't2', agentId: 'moa' })
    recordToolPhaseFrame(toolFrame('c1', 'read_file', 'running', 'moa'))
    render(<ChatMessageList {...streamingProps()} />)
    expect(screen.queryByTestId('running-badge-pill')).toBeNull()
  })

  it('a CLI seat emits no tool_status, so its badge correctly stays hidden', () => {
    // agentKind: 'cli' — `kind_bases.py` only attaches the turn-phase hooks on
    // the API path, so this turn never produces a phase frame. The badge must
    // NOT be faked from `streaming`.
    recordTurnFrame({ kind: 'turn_started', turnId: 't1', agentId: 'codey' })
    render(<ChatMessageList {...streamingProps({ agentKind: 'cli', isApiAgent: false })} />)
    expect(screen.queryByTestId('running-badge-pill')).toBeNull()
    expect(screen.getByTestId('agent-row-stop')).toBeTruthy()
  })

  it('the awaiting-first-token row follows the same split', () => {
    recordTurnFrame({ kind: 'turn_started', turnId: 't1', agentId: 'codey' })
    render(<ChatMessageList {...baseProps({ awaitingAssistant: true })} />)
    // Eye-dots only while waiting on the model …
    expect(screen.getByTestId('composer-working-indicator')).toBeTruthy()
    expect(screen.queryByTestId('running-badge-pill')).toBeNull()

    // … badge when a tool call is in flight …
    act(() => {
      recordToolPhaseFrame(toolFrame('c1', 'bash', 'running', 'codey'))
    })
    expect(screen.getByTestId('running-badge-pill')).toHaveTextContent('Running · bash')
  })
})

describe('#1684: the stop button has two hover targets and one rule', () => {
  it('hovering the badge reveals it (target b, unchanged)', () => {
    render(<ChatMessageList {...streamingProps()} />)
    const badgeWrap = screen.getByTestId('running-status-badge')
    const stop = screen.getByTestId('agent-row-stop')
    expect(stop).toHaveAttribute('data-visible', 'false')
    fireEvent.mouseEnter(badgeWrap)
    expect(stop).toHaveAttribute('data-visible', 'true')
    fireEvent.mouseLeave(badgeWrap)
    expect(stop).toHaveAttribute('data-visible', 'false')
  })

  it('hovering the avatar eye-dots reveals the same control (target a, new)', () => {
    recordTurnFrame({ kind: 'turn_started', turnId: 't1', agentId: 'codey' })
    recordToolPhaseFrame(toolFrame('c1', 'read_file', 'running', 'codey'))
    render(<ChatMessageList {...streamingProps()} />)

    const eyeDots = screen.getByTestId('composer-working-indicator')
    const badgeWrap = screen.getByTestId('running-status-badge')
    const stop = screen.getByTestId('agent-row-stop')
    // The two targets are genuinely different elements: the eye-dots are
    // inside the bubble, the badge is the slot below it.
    expect(eyeDots).not.toBe(badgeWrap)
    expect(eyeDots.contains(badgeWrap)).toBe(false)
    expect(badgeWrap.contains(eyeDots)).toBe(false)
    expect(stop).toHaveAttribute('data-visible', 'false')

    fireEvent.mouseEnter(eyeDots)
    // Lands on the SAME shared class the badge's own hover produces, so
    // `index.css` keeps one reveal rule rather than a parallel copy.
    expect(badgeWrap).toHaveClass('os-running-stop--revealed')
    expect(badgeWrap).toHaveAttribute('data-revealed', 'true')
    expect(stop).toHaveAttribute('data-visible', 'true')

    fireEvent.mouseLeave(eyeDots)
    expect(badgeWrap).not.toHaveClass('os-running-stop--revealed')
    expect(stop).toHaveAttribute('data-visible', 'false')
  })

  it('the awaiting row eye-dots are the second target there too', () => {
    render(<ChatMessageList {...baseProps({ awaitingAssistant: true })} />)
    const eyeDots = screen.getByTestId('composer-working-indicator')
    const stop = screen.getByTestId('agent-row-stop')
    expect(stop).toHaveAttribute('data-visible', 'false')
    fireEvent.mouseEnter(eyeDots)
    expect(screen.getByTestId('running-status-badge')).toHaveAttribute('data-revealed', 'true')
    expect(stop).toHaveAttribute('data-visible', 'true')
    fireEvent.mouseLeave(eyeDots)
    expect(stop).toHaveAttribute('data-visible', 'false')
  })
})

/**
 * TASK 5 — the orphaned streaming row, demonstrated WITHOUT editing
 * `ChatPage.tsx`.
 *
 * `ChatPage.tsx:2404-2418` (`attachToolToThread`) synthesises an assistant
 * row with `streaming: true` when a tool lands before any assistant text
 * exists. Nothing ever clears that flag: it is `assistant_final` — or, in
 * today's code, merely a *later* `assistant_start` that appends a second row
 * — that heals it. `ChatPage.tsx` is out of scope here, so the row is
 * reproduced here exactly as that code creates it.
 *
 * What the test shows: the orphan is the last assistant row, so it becomes the
 * badge host; while the tool is genuinely in flight the badge it shows is
 * CORRECT. The defect is the row's `streaming: true` outliving the turn —
 * after `turn_finished` the registry has no tool, yet the row still renders
 * the permanent "this turn is live" chrome (eye-dots + a mounted stop slot)
 * with nothing behind them. Under the pre-#1684 flag that same stale row held
 * a "Running" badge open forever; decoupling the badge removes that, but the
 * stale row itself is still `ChatPage`'s to fix.
 */
describe('#1684: the orphaned tool-host row (ChatPage handoff, NOT fixed here)', () => {
  const ORPHAN = {
    key: 'tool-host-call-1',
    role: 'assistant',
    text: '',
    streaming: true,
    ts: '2026-09-26T08:00:00Z',
  }

  const orphanProps = (extra: Record<string, any> = {}) =>
    baseProps({
      messages: [ORPHAN],
      displayItems: [{ kind: 'message', message: ORPHAN }],
      ...extra,
    })

  it('badges correctly while the tool is actually in flight', () => {
    recordTurnFrame({ kind: 'turn_started', turnId: 't1', agentId: 'codey' })
    recordToolPhaseFrame(toolFrame('call-1', 'handoff', 'running', 'codey'))
    render(<ChatMessageList {...orphanProps()} />)
    // The badge is on the tool phase, not on the row's `streaming` flag.
    expect(screen.getByTestId('running-badge-pill')).toHaveTextContent('Running · handoff')
  })

  it('the badge clears when the turn ends, but the orphan row stays stuck on streaming', () => {
    recordTurnFrame({ kind: 'turn_started', turnId: 't1', agentId: 'codey' })
    recordToolPhaseFrame(toolFrame('call-1', 'handoff', 'running', 'codey'))
    render(<ChatMessageList {...orphanProps()} />)
    expect(screen.getByTestId('running-badge-pill')).toBeTruthy()

    act(() => {
      recordToolPhaseFrame(toolFrame('call-1', 'handoff', 'done', 'codey'))
      recordTurnFrame({ kind: 'turn_finished', turnId: 't1', agentId: 'codey' })
    })

    // Never-stuck: the badge is gone.
    expect(screen.queryByTestId('running-badge-pill')).toBeNull()

    // The remaining defect, owned by ChatPage.tsx:2404-2418 — `streaming: true`
    // on this synthetic row is never cleared, so the row still claims "a turn
    // is live" with no turn behind it. Pre-#1684 this row ALSO held a Running
    // badge open indefinitely; the decoupling removes the badge, not the
    // orphaned row.
    expect(screen.getByTestId('composer-working-indicator')).toBeTruthy()
    expect(screen.getByTestId('agent-row-stop-slot')).toBeTruthy()
  })
})
