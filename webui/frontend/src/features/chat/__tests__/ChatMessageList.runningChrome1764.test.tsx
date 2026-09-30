/**
 * #1764 — ONE place says "Running", and a direct chat says none of them.
 *
 * #1684 already decoupled the under-message pill from the avatar's eye-dots.
 * Three chrome sites were left, and together they are the stacked spinners in
 * the ticket's screenshot:
 *
 *   1. the bottom **fan-out card stack**. A team send to a single CLI/remote
 *      member still runs through the roster executor
 *      (`team_roster_executor.team_send_fans_out`: "a single CLI or remote
 *      member still uses the executor"), which emits `fan_out_leg` frames and
 *      therefore a card badged **Running** under the transcript. That leg IS
 *      the seat being talked to, so the card is this conversation restated.
 *   2. the **in-bubble `ToolCallPopup` status badge**, which repeats "Running"
 *      for the very tool the under-message pill already names as
 *      `Running · <tool>` — two identical pills for one call.
 *   3. the stack is **never cleared** except by Stop, so a leg whose terminal
 *      frame never landed (socket died mid-leg) left "Running" sitting under a
 *      turn that had already ended.
 *
 * Success 1/2/3 of the issue, driven through `ChatMessageList` with the real
 * registry and the real `ToolCallPopup`, so no server and no `ChatPage` needed.
 */
import { render, screen, act } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatMessageList } from '../ChatMessageList'
import ToolCallPopup from '../../../components/ToolCallPopup'
import {
  recordToolPhaseFrame,
  recordTurnFrame,
  resetTurnRegistry,
  type ToolPhaseFrame,
} from '../../../lib/agentTurns'
import type { BubbleTheme } from '../../../lib/bubbleTheme'
import type { FanOutLeg } from '../../../lib/runningCards'

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

const DIRECT_REPLY = {
  key: 'assistant-1',
  role: 'assistant',
  text: 'Sure — here is the longer version.',
  streaming: true,
  ts: '2026-09-30T08:00:00Z',
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
    // The REAL popup: the duplicated "Running" badge lives inside it, so a stub
    // would hide the very defect this file reproduces.
    ToolCallPopup,
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
    activeChatAgentId: 'rig-alpha',
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
    selectedBlueprint: '',
    selectedTeam: null,
    showCliSessionRecovery: false,
    showSupportJourneyChips: false,
    skillCatalog: [],
    streamingMessage: DIRECT_REPLY,
    summaryMap: {},
    supportJourneyChips: [],
    teamChatMemberId: 'codey',
    teamFromUrl: 'rig-alpha',
    threadKey: 'rig-alpha',
    threadReady: true,
    voiceBind: null,
    workingTip: 'Thinking…',
    ...overrides,
  } as any
}

const directProps = (overrides: Record<string, any> = {}) =>
  baseProps({
    messages: [DIRECT_REPLY],
    displayItems: [{ kind: 'message', message: DIRECT_REPLY }],
    ...overrides,
  })

/**
 * Every literal "Running" affordance on screen at once, whatever component it
 * belongs to. The issue is about COUNT, so the assertion is about count — a
 * future second site cannot slip past a test that only knows one testid.
 */
function runningAffordances(): HTMLElement[] {
  const byTestId = [
    ...screen.queryAllByTestId('running-badge-pill'),
    ...screen.queryAllByTestId('running-card-status'),
    ...screen.queryAllByTestId('tool-status-badge'),
  ].filter((el) => el.getAttribute('data-status') !== 'done')
  // `querySelectorAll<HTMLElement>` so the leaf-text scan is typed as the
  // HTMLElement[] this function returns, instead of the wider Element[] the
  // untyped overload hands back.
  const byText = Array.from(document.querySelectorAll<HTMLElement>('*')).filter((el) => {
    if (el.children.length > 0) return false
    return (el.textContent || '').trim() === 'Running'
  })
  return [...byTestId, ...byText]
}

/** One roster executor leg — the single-member run a direct chat produces. */
const directMemberLeg: FanOutLeg = {
  id: 'codey',
  label: 'Codey',
  status: 'running',
  kind: 'cli',
  openId: 'codey',
  batchId: 'b1',
}

/** A real fan-out: the operator's own seat plus two siblings. */
const siblingLegs: FanOutLeg[] = [
  directMemberLeg,
  { ...directMemberLeg, id: 'stewie', label: 'Stewie', openId: 'stewie' },
  { ...directMemberLeg, id: 'rue', label: 'Rue', openId: 'rue' },
]

beforeEach(() => {
  resetTurnRegistry()
})

describe('#1764 Success 1: a direct agent reply shows NO Running pill anywhere', () => {
  it('a plain streaming direct reply shows only the animated avatar', () => {
    recordTurnFrame({ kind: 'turn_started', turnId: 't1', agentId: 'codey' })
    render(<ChatMessageList {...directProps()} />)

    // The animated avatar / in-bubble ellipsis is the whole affordance.
    expect(screen.getByTestId('composer-working-indicator')).toBeTruthy()
    // …and not one word of "Running" is on screen.
    expect(runningAffordances()).toEqual([])
    expect(screen.queryByTestId('running-badge-pill')).toBeNull()
    expect(screen.queryByTestId('running-card-stack')).toBeNull()
  })

  it('the roster executor leg for the seat being talked to gets NO bottom card', () => {
    recordTurnFrame({ kind: 'turn_started', turnId: 't1', agentId: 'codey' })
    // A direct chat to a CLI/remote member runs through `execute_roster` and
    // emits exactly one `fan_out_leg`. Before #1764 that produced a card badged
    // "Running" at the foot of the transcript — the bottom-bar Running pill.
    render(<ChatMessageList {...directProps({ fanOutLegs: [directMemberLeg] })} />)

    expect(screen.queryByTestId('running-card-stack')).toBeNull()
    expect(runningAffordances()).toEqual([])
  })

  it('an idle seat shows nothing at all', () => {
    const done = { ...DIRECT_REPLY, streaming: false }
    render(
      <ChatMessageList
        {...baseProps({
          messages: [done],
          displayItems: [{ kind: 'message', message: done }],
          streamingMessage: null,
          fanOutLegs: [],
        })}
      />,
    )
    expect(screen.queryByTestId('composer-working-indicator')).toBeNull()
    expect(runningAffordances()).toEqual([])
  })
})

describe('#1764 Success 2: exactly ONE Running affordance when a tool is in flight', () => {
  it('the under-message pill names the tool; the in-bubble popup stops repeating it', () => {
    recordTurnFrame({ kind: 'turn_started', turnId: 't1', agentId: 'codey' })
    const withTool = {
      ...DIRECT_REPLY,
      tools: [{ id: 'c1', name: 'read_file', status: 'running', needsApproval: false }],
    }
    render(
      <ChatMessageList
        {...directProps({
          messages: [withTool],
          displayItems: [{ kind: 'message', message: withTool }],
          streamingMessage: withTool,
        })}
      />,
    )

    act(() => {
      recordToolPhaseFrame(toolFrame('c1', 'read_file', 'running', 'codey'))
    })

    // The chosen single place: the pill under the message row.
    const pills = screen.getAllByTestId('running-badge-pill')
    expect(pills).toHaveLength(1)
    expect(pills[0]).toHaveTextContent('Running · read_file')

    // The popup still records the call (its name is the audit trail) but no
    // longer paints a second "Running" badge for the same call.
    expect(screen.getByText('read_file')).toBeTruthy()
    expect(runningAffordances()).toHaveLength(1)
  })

  it('the popup keeps its own Running badge when no row pill is covering the call', () => {
    // A tool row with no live turn (a late frame, a different seat, a CLI seat
    // that emits no phase): nothing else says "Running", so the popup must.
    const withTool = {
      ...DIRECT_REPLY,
      tools: [{ id: 'c1', name: 'read_file', status: 'running', needsApproval: false }],
    }
    render(
      <ChatMessageList
        {...directProps({
          messages: [withTool],
          displayItems: [{ kind: 'message', message: withTool }],
          streamingMessage: withTool,
        })}
      />,
    )
    expect(screen.queryByTestId('running-badge-pill')).toBeNull()
    expect(screen.getByTestId('tool-status-badge')).toHaveAttribute('data-status', 'running')
    // tool-status-badge + its leaf text both match runningAffordances(); the
    // contract is exactly one Running site — the popup badge.
    expect(screen.getAllByTestId('tool-status-badge')).toHaveLength(1)
  })

  it('a real fan-out keeps one card per SIBLING, and never a card for this seat', () => {
    recordTurnFrame({ kind: 'turn_started', turnId: 't1', agentId: 'codey' })
    render(<ChatMessageList {...directProps({ fanOutLegs: siblingLegs })} />)

    expect(screen.queryByTestId('running-card-stack')).toBeTruthy()
    expect(screen.getAllByTestId('running-card-name').map((el) => el.textContent)).toEqual([
      'Stewie',
      'Rue',
    ])
    // Two sibling rows, and zero pills for the operator's own seat.
    // Count card status nodes only — leaf text nodes also say "Running".
    expect(screen.getAllByTestId('running-card-status')).toHaveLength(2)
    expect(screen.queryByTestId('running-badge-pill')).toBeNull()
  })

  it('a sibling fan-out plus a tool in flight still shows the tool pill once', () => {
    recordTurnFrame({ kind: 'turn_started', turnId: 't1', agentId: 'codey' })
    render(<ChatMessageList {...directProps({ fanOutLegs: siblingLegs })} />)
    act(() => {
      recordToolPhaseFrame(toolFrame('c1', 'bash', 'running', 'codey'))
    })
    const pills = screen.getAllByTestId('running-badge-pill')
    expect(pills).toHaveLength(1)
    expect(pills[0]).toHaveTextContent('Running · bash')
  })
})

describe('#1764 Success 3: completed turns clear the chrome promptly', () => {
  it('the tool terminal frame leaves the row with only its eye-dots', () => {
    recordTurnFrame({ kind: 'turn_started', turnId: 't1', agentId: 'codey' })
    render(<ChatMessageList {...directProps()} />)
    act(() => {
      recordToolPhaseFrame(toolFrame('c1', 'read_file', 'running', 'codey'))
    })
    expect(screen.getByTestId('running-badge-pill')).toBeTruthy()

    act(() => {
      recordToolPhaseFrame(toolFrame('c1', 'read_file', 'done', 'codey'))
      recordTurnFrame({ kind: 'turn_finished', turnId: 't1', agentId: 'codey' })
    })
    expect(screen.queryByTestId('running-badge-pill')).toBeNull()
    expect(screen.getByTestId('composer-working-indicator')).toBeTruthy()
  })
})
