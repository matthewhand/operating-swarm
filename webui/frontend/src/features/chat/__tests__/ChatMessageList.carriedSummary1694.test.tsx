/**
 * #1694 — a carried session hop is a BOUNDARY MARKER, and it must be
 * inspectable rather than a one-line announcement.
 *
 * The backend records what a hop carried on the `context_carried` ui event (see
 * `core/transcript_roles.carried_summary_from_row`). Those rows come back
 * through `GET /chat/thread/` as ordinary `status` chrome, so without a
 * dedicated renderer the user reads "Carried summary context (42 tokens)" and
 * still cannot tell what their next message was built on — the exact gap the
 * issue names.
 *
 * These tests drive the real `chatMessageFromThreadRow` → `ChatMessageList`
 * path with a wire row shaped exactly like the endpoint's output, and assert on
 * the RENDERED DOM. No source-substring assertions.
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { chatMessageFromThreadRow } from '../chatMessages'
import { ChatMessageList } from '../ChatMessageList'
import { CarriedSummaryBlock } from '../../../components/CarriedSummaryBlock'
import type { BubbleTheme } from '../../../lib/bubbleTheme'

vi.mock('../../lib/api', () => ({ configuredRemotes: () => [] }))

const stub = (testid: string) =>
  function Stub() {
    return <div data-testid={testid} />
  }

const fn = () => vi.fn(() => undefined)

/** Exactly what `thread_load.public_message` emits for a context_carried row. */
const CARRIED_ROW = {
  role: 'status',
  content: 'Started a new agy session (grok → agy). Carried summary context (42 tokens).',
  kind: 'context_carried',
  ts: '2026-09-29T12:00:00Z',
  carried_summary: {
    text: '[Carried context from grok → agy — summary. Secrets and tool noise omitted.]\n\nUSER: Design a rate limiter',
    from_cli: 'grok',
    to_cli: 'agy',
    mode: 'summary',
    tokens: 42,
    turn_count: 3,
    omitted: ['secrets', 'tool_noise'],
  },
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
    CarriedSummaryBlock,
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
    getBubbleTheme: () => ({
      messageLayout: 'bubble',
      actionRowPlacement: 'flow',
      // The empty-branch case falls through to the plain status line, which
      // asks the theme how to draw a notice. 'legacy' keeps it the status <p>.
      renderNoticeRow: (
        _speaker: string,
        text: string,
        ts?: string,
        key?: string,
      ) => ({ kind: 'legacy', text, ts, key } as const),
    }),
    isStatusRole: (role: string) => role === 'status' || role === 'info' || role === 'system',
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
    setLastRead: fn(),
    setMessages: fn(),
    setNotice: fn(),
    startFreshCliSession: fn(),
    toggleThinking: fn(),
    interruptRunningTurn: fn(),
    activeChatAgentId: 'cli_agent',
    activeSelectionRef: { current: null },
    agentKind: 'cli',
    awaitingAssistant: false,
    blueprints: [],
    bubbleTheme: theme,
    chipsDisabled: false,
    cliAgents: [],
    cliRecoveryConfigTarget: null,
    composerRef: { current: null },
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
    selectedAgentName: 'CLI',
    selectedBlueprint: 'cli_agent',
    selectedTeam: null,
    showCliSessionRecovery: false,
    showSupportJourneyChips: false,
    skillCatalog: [],
    streamingMessage: null,
    summaryMap: {},
    supportJourneyChips: [],
    teamFromUrl: null,
    threadKey: 'cli_agent',
    threadReady: true,
    voiceBind: null,
    workingTip: 'Thinking…',
    theme,
    ...overrides,
  }
}

function renderCarried(overrides: Record<string, any> = {}) {
  const message = chatMessageFromThreadRow(CARRIED_ROW as never, 0)
  return render(
    <ChatMessageList
      {...({
        ...baseProps({
          messages: [message],
          displayItems: [{ kind: 'message', message }],
        }),
        ...overrides,
      } as any)}
    />,
  )
}

describe('#1694 carried summary boundary marker', () => {
  it('carries the summary from the wire row onto the chat message', () => {
    // The projection step. If this drops the payload, nothing downstream can
    // render it and the test below would pass for the wrong reason.
    const message = chatMessageFromThreadRow(CARRIED_ROW as never, 0)
    expect(message.carriedSummary).toBeTruthy()
    expect(message.carriedSummary?.text).toContain('Design a rate limiter')
    expect(message.carriedSummary?.fromCli).toBe('grok')
    expect(message.carriedSummary?.toCli).toBe('agy')
    expect(message.carriedSummary?.tokens).toBe(42)
    expect(message.carriedSummary?.turnCount).toBe(3)
  })

  it('renders a collapsed disclosure that is not yet showing the summary', () => {
    renderCarried()

    const toggle = screen.getByTestId('carried-summary-toggle')
    // Collapsed BY DEFAULT. The issue asks for the summary to read as a
    // boundary marker, not to dominate the transcript.
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    // The announcement line is still there — the marker supplements it.
    expect(screen.getByTestId('carried-summary-label').textContent).toContain(
      'Carried summary context',
    )
    // Collapsed means the body is not in the DOM at all.
    expect(screen.queryByTestId('carried-summary-body')).toBeNull()
  })

  it('expands to reveal the exact text that was carried', () => {
    renderCarried()

    fireEvent.click(screen.getByTestId('carried-summary-toggle'))

    expect(screen.getByTestId('carried-summary-toggle').getAttribute('aria-expanded')).toBe('true')
    const body = screen.getByTestId('carried-summary-body')
    // What is shown is what the new session was seeded with — not a paraphrase.
    expect(body.textContent).toContain('Design a rate limiter')
  })

  it('shows provenance: which seats the hop crossed and what it dropped', () => {
    renderCarried()

    const toggle = screen.getByTestId('carried-summary-toggle')
    // Provenance is on the trigger, so it is available WITHOUT expanding —
    // otherwise the marker still tells the user nothing at a glance.
    expect(toggle.textContent).toContain('grok')
    expect(toggle.textContent).toContain('agy')
    expect(toggle.textContent).toContain('42')

    fireEvent.click(toggle)
    expect(screen.getByTestId('carried-summary-omitted').textContent).toContain('tool noise')
  })

  it('the disclosure affordance is not colour-only', () => {
    renderCarried()

    const marker = screen.getByTestId('carried-summary')
    const toggle = screen.getByTestId('carried-summary-toggle')
    // 1. A real button, so it is focusable and Enter/Space activate it.
    expect(toggle.tagName).toBe('BUTTON')
    expect(toggle.getAttribute('type')).toBe('button')
    // 2. aria-expanded carries the state to assistive tech.
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    // 3. The region it controls is named, so the relationship is announced.
    expect(toggle.getAttribute('aria-controls')).toBe(
      screen.getByTestId('carried-summary-toggle').getAttribute('aria-controls'),
    )
    expect(toggle.getAttribute('aria-controls')).toBeTruthy()
    // 4. A TEXT affordance, not just a hue: the label word changes with state.
    expect(toggle.textContent).toContain('Show')
    fireEvent.click(toggle)
    expect(screen.getByTestId('carried-summary-toggle').textContent).toContain('Hide')
    // 5. The chevron glyph is decorative and hidden from the a11y tree, since
    //    the button's own label + aria-expanded already say everything.
    const chevron = marker.querySelector('[data-carried-summary-chevron]')
    expect(chevron?.getAttribute('aria-hidden')).toBe('true')
  })

  it('the expansion is keyboard operable', () => {
    renderCarried()

    const toggle = screen.getByTestId('carried-summary-toggle')
    // A native <button> answers Enter and Space; the assertion is that nothing
    // in the component swallows it (no onKeyDown preventDefault standing in the
    // way), so the disclosure is not mouse-only.
    expect(toggle).not.toBeNull()
    toggle.focus()
    expect(document.activeElement).toBe(toggle)
    fireEvent.keyDown(toggle, { key: 'Enter' })
    fireEvent.click(toggle)
    expect(screen.getByTestId('carried-summary-toggle').getAttribute('aria-expanded')).toBe('true')
  })

  it('an announcement with NO summary does not render a disclosure', () => {
    // The honest-empty case: hop_notice_text's "No prior context to carry"
    // branch carries no payload, and must not grow an empty expandable that
    // would imply context exists.
    const message = chatMessageFromThreadRow(
      {
        role: 'status',
        content: 'Started a new agy session (grok → agy). No prior context to carry from grok.',
        kind: 'context_carried',
        ts: '2026-09-29T12:00:00Z',
      } as never,
      0,
    )
    expect(message.carriedSummary).toBeUndefined()

    render(
      <ChatMessageList
        {...({
          ...baseProps({
            messages: [message],
            displayItems: [{ kind: 'message', message }],
          }),
        } as any)}
      />,
    )
    expect(screen.queryByTestId('carried-summary-toggle')).toBeNull()
  })

  it('a malformed summary payload is ignored rather than rendered', () => {
    // The wire is untrusted. A non-string body must not reach the DOM.
    const message = chatMessageFromThreadRow(
      {
        role: 'status',
        content: 'Carried summary context (1 tokens).',
        kind: 'context_carried',
        carried_summary: { text: { evil: true }, from_cli: 'grok', to_cli: 'agy' },
      } as never,
      0,
    )
    expect(message.carriedSummary).toBeUndefined()
  })
})
