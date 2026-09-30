/**
 * D1 — the per-agent Stop control aligns to the message content axis for the
 * active bubble theme.
 *
 * The stop renders after the streaming assistant bubble. Previously the slot
 * was flush to the row's far left (`flex justify-start`), so on the speech
 * theme it sat under the beside-bubble avatar and on IRC it sat left of the
 * resizable name gutter — disconnected from the message input's text axis.
 *
 * The slot now carries a per-theme axis contract:
 *   • `data-stop-axis="bubble"` (speech/simple) — indented to the bubble's
 *     content column (2rem past the avatar for speech, flush for simple).
 *   • `data-stop-axis="line"` (IRC) — indented past the timestamp/name gutter.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { ChatMessageList } from '../ChatMessageList'
import { getBubbleTheme, type BubbleTheme } from '../../../lib/bubbleTheme'
import { isStatusRole } from '../../../lib/chatStatus'
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

function baseProps(theme: BubbleTheme) {
  const messages = [
    {
      key: 'assistant-streaming-1',
      role: 'assistant',
      text: 'partial answer',
      streaming: true,
      ts: '2026-09-26T08:00:00Z',
    },
  ]
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
    agentIdFromBlueprint,
    extractThinkingBlock,
    getBubbleTheme,
    isStatusRole,
    personaForAgentMessage: () => null,
    rawOffsetForMessage,
    themeUsesIrcGutter: (t: string) => t === 'irc',
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
  } as any
}

const EXPECTED_AXIS: Record<BubbleTheme, 'bubble' | 'line'> = {
  speech: 'bubble',
  simple: 'bubble',
  irc: 'line',
}

describe('D1 stop control axis per bubble theme', () => {
  for (const theme of ['speech', 'simple', 'irc'] as BubbleTheme[]) {
    it(`${theme}: slot carries data-stop-axis="${EXPECTED_AXIS[theme]}"`, () => {
      render(<ChatMessageList {...baseProps(theme)} />)
      const slot = screen.getByTestId('agent-row-stop-slot')
      expect(slot).toHaveAttribute('data-stop-axis', EXPECTED_AXIS[theme])
      expect(slot).toHaveClass(`os-agent-row__stop-slot--${EXPECTED_AXIS[theme]}`)
      // The contract keys off the theme's own message layout — not a
      // hard-coded theme list — so a new theme cannot silently opt out.
      const expected =
        getBubbleTheme(theme).messageLayout === 'line' ? 'line' : 'bubble'
      expect(slot).toHaveAttribute('data-stop-axis', expected)
    })
  }

  it('keeps the testid, aria-label and interrupt handler on the stop button', () => {
    render(<ChatMessageList {...baseProps('speech')} />)
    // #1684: the slot still exists and still carries the stop control, but its
    // "Running" pill is the tool-in-flight mark — and this fixture has no tool
    // in flight (plain streaming), so the badge copy is correctly absent. The
    // axis contract this file pins is the slot, which is unchanged.
    const badge = screen.getByTestId('running-status-badge')
    expect(screen.queryByTestId('running-badge-pill')).toBeNull()
    expect(badge.querySelector('.loading-spinner')).toBeNull()
    const stop = screen.getByTestId('agent-row-stop')
    expect(stop).toHaveAttribute('aria-label', 'Stop generating')
    expect(stop).toHaveAttribute('data-visible', 'false')
    expect(screen.getByText('Stop')).toHaveClass('os-agent-row__stop-label')
  })

  it('CSS aligns the slot to the per-theme content axis', () => {
    const css = readFileSync(join(process.cwd(), 'src/index.css'), 'utf8')
    expect(css).toMatch(
      /\.os-agent-row__stop-slot\s*\{[^}]*padding-inline-start:\s*var\(--os-stop-axis-offset/s,
    )
    expect(css).toMatch(
      /\[data-bubble-theme="speech"\]\s+\.os-agent-row__stop-slot\s*\{[^}]*--os-stop-axis-offset:\s*2rem/s,
    )
    expect(css).toMatch(
      /\[data-message-layout="line"\]\s+\.os-agent-row__stop-slot\s*\{[^}]*--os-stop-axis-offset:\s*calc\(var\(--irc-gutter-px/s,
    )
  })
})
