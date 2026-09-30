/**
 * #856 slice F — the chat message list, moved verbatim from ChatPage.tsx.
 *
 * Renders the scrollable message surface: restore/hydrate states, empty
 * states (demo + support journeys), the summary/message/fan-out row loop
 * with per-row actions, the CLI recovery banner, the inline working
 * indicator, #1374 stacked Running cards for a fan-out's live legs,
 * and the scroll-anchor. ChatPage owns all state and passes it
 * down as one props object.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- pass-through props during extraction
import { forwardRef, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { SubagentFanOutData } from '../../lib/subagentFanOut'
import { interleaveTimelineMarkers, type TimelineMarker } from '../../lib/chatTimeline'
import { BlueprintTip } from '../../components/BlueprintTip'
import {
  blueprintTipKindFor,
  hydrateBlueprintTipsDismissed,
  isBlueprintTipDismissed,
  persistBlueprintTipDismissed,
  type BlueprintTipKind,
} from '../../lib/blueprintTips'
import { isExperimentalFeatureEnabled } from '../../lib/experimentalFeatures'
import MessageReactionPills from '../../components/MessageReactionPills'
import { RunningStopBadge } from '../../components/RunningStopBadge'
import RunningCard from '../../components/RunningCard'
import { cardsForFanOutLegs } from '../../lib/runningCards'
import { useActiveToolForAgent } from '../../lib/agentTurns'
import {
  THREAD_LOADING_LABEL,
  THREAD_STALE_LABEL,
  threadLoadPhase,
} from './threadLoadState'

export interface ChatMessageListProps {
  [key: string]: any
}

/**
 * #1684: reveal-state key for the standalone "awaiting first token" row.
 * It has no message key of its own, so it gets a sentinel that can never
 * collide with a transcript row key.
 */
const AWAITING_ROW_KEY = '__os-awaiting-row__'

/* #1371: the per-agent Stop (abort/cancel-turn) control is not standing chrome.
   `RunningStopBadge` (components/RunningStopBadge.tsx) owns the reveal: it is
   concealed at rest and only becomes visible while the Running badge — the
   working avatar + spinner that marks the generating agent — is hovered or
   holds keyboard focus. The button stays mounted at all times, so revealing it
   never reflows the row, and it stays reachable by Tab. #1630: the previous
   Tailwind-class duplicate of that contract was dead code once the badge took
   over; the reveal now lives in one place (the badge) plus its `index.css`
   rules, so this module no longer carries a class string of its own. */

export const ChatMessageList = forwardRef<HTMLDivElement, ChatMessageListProps>(
  function ChatMessageList(props, _ref) {
    const {
    AgentAvatar,
    ChatMessageActions,
    ChatMessageBubble,
    ChatNewRule,
    CliSessionRecoveryBanner,
    DemoTourBanner,
    IrcNoticeLine,
    MessageRowActions,
    PrOpenedCard,
    QuestionCard,
    RateLimitStatusLine,
    ReadAloudButton,
    SHOW_MESSAGE_ACTIONS,
    START_CONTEXT_FROM_HERE_LABEL,
    SubagentFanOutBlock,
    SuggestionChips,
    SummaryBlock,
    SystemPreloadPill,
    TeammateTaskCard,
    ToolCallPopup,
    activeChatAgentId,
    activeSelectionRef,
    agentIdFromBlueprint,
    agentKind,
    attachToolToThread,
    awaitingAssistant,
    blueprints,
    bubbleTheme,
    cacheRowSelection,
    // #1694: injected like its sibling SummaryBlock (the #856 extraction
    // slice keeps every card component a prop, so ChatPage owns the wiring).
    CarriedSummaryBlock,
    chipsDisabled,
    chooseSuggestion,
    clearCliSessionHistory,
    cliAgents,
    cliRecoveryConfigTarget,
    composerRef,
    configuredRemotes,
    contextMeta,
    contextStrategy,
    conversationId,
    demoMode,
    displayItems,
    editedAgentLabel,
    editingKey,
    expandedThinkingKeys,
    extractThinkingBlock,
    formatGapLabel,
    formatRateLimitNotice,
    getBubbleTheme,
    handleBubbleContextMenu,
    handleContextToHere,
    handleSaveSummary,
    handleToggleSummaryContext,    hiddenMessageKeys,
    onResendSend,
    hiddenSummaryIds,
    hydrateError,
    isApiAgent,
    isHerdrSeat,
    isStatusRole,
    jumpToPrOpener,
    lastUserTextRef,
    listEndRef,
    messages,
    messagesEditable,
    newBeforeKey,
    nowMs,
    openSettingsSheet,
    parseCreatedAtMs,
    personaForAgentMessage,
    rawOffsetForMessage,
    rememberAlwaysAllow,
    remotesListQuery,
    resolveReplyQuote,
    restoreNotice,
    retryCliSession,
    saveEditedMessage,
    toggleMessageReaction,
    selectedAgent,
    selectedAgentName,
    selectedBlueprint,
    selectedTeam,
    sendQuestionAnswer,
    sendText,
    sendToolDecision,
    setEditingKey,
    setHiddenMessageKeys,
    setHiddenSummaryIds,
    setOpenSkillName,
    setRawResponseModalText,
    setReplyTarget,
    setThreads,
    settingsTargetForProvider,
    showCliSessionRecovery,
    showSupportJourneyChips,
    showGettingStartedFlow,
    gettingStartedFlow,
    gettingStartedChips,
    skillCatalog,
    startFreshCliSession,
    streamingMessage,
    summaryMap,
    supportJourneyChips,
    teamFromUrl,
    teamChatMemberId,
    themeUsesIrcGutter,
    threadKey,
    threadReady,
    toggleThinking,
    voiceBind,
    workingTip,
    interruptRunningTurn,
    fanOutLegs,
    stopFanOutLeg,
  } = props as Record<string, any>

    // #1319: newest-first hydration paging. The parent owns the transcript and
    // the fetch; this list only renders the "Load earlier messages" affordance
    // and anchors the scroll position so prepending an older page does not
    // jump the viewport. `scrollBoxRef` is the ChatTranscriptShell scroll
    // container passed down through the shared props bag.
    const hasEarlierMessages = props.hasEarlierMessages === true
    const loadingEarlierMessages = props.loadingEarlierMessages === true
    const onLoadEarlierMessages = props.onLoadEarlierMessages as (() => void) | undefined
    const scrollBoxRef = props.scrollBoxRef as { current: HTMLElement | null } | undefined
    const earlierAnchorRef = useRef<{ height: number; top: number } | null>(null)

    const stopLeg = typeof stopFanOutLeg === 'function' ? stopFanOutLeg : undefined

    // #1684 / #1764: tool-in-flight signal for THIS row's agent. Prefer the
    // team member being talked to over the team id — otherwise a direct
    // Codey chat on a team looks up tools under the rig id and never badges.
    const rowAgentId: string | null =
      (typeof teamChatMemberId === 'string' && teamChatMemberId.trim()
        ? teamChatMemberId.trim()
        : null) ||
      (teamFromUrl as string | null) ||
      (typeof agentIdFromBlueprint === 'function'
        ? (agentIdFromBlueprint(selectedBlueprint) as string | null)
        : null) ||
      (activeChatAgentId as string | null) ||
      null
    const activeTool = useActiveToolForAgent(rowAgentId)
    const activeToolName = activeTool?.name ?? null

    // #1764: bottom Running cards are for SIBLINGS only. The seat under chat
    // already has avatar + (when needed) the under-message pill.
    const fanOutCards = useMemo(
      () =>
        cardsForFanOutLegs(Array.isArray(fanOutLegs) ? fanOutLegs : [], {
          excludeSeatIds: [teamChatMemberId, activeChatAgentId, rowAgentId],
        }),
      [fanOutLegs, teamChatMemberId, activeChatAgentId, rowAgentId],
    )

    // #1684: reveal state, shared by the two hover targets. `null` = neither.
    const [revealKey, setRevealKey] = useState<string | null>(null)
    const revealRow = useCallback((key: string) => setRevealKey(key), [])
    const concealRow = useCallback(
      (key: string) => setRevealKey((prev) => (prev === key ? null : prev)),
      [],
    )

    const handleLoadEarlier = () => {
      const box = scrollBoxRef?.current
      if (box) {
        earlierAnchorRef.current = { height: box.scrollHeight, top: box.scrollTop }
      }
      onLoadEarlierMessages?.()
    }

    useLayoutEffect(() => {
      const anchor = earlierAnchorRef.current
      if (!anchor) return
      // Wait for the in-flight older page before re-anchoring.
      if (loadingEarlierMessages) return
      earlierAnchorRef.current = null
      const box = scrollBoxRef?.current
      if (!box) return
      const delta = box.scrollHeight - anchor.height
      if (delta > 0) box.scrollTop = anchor.top + delta
    }, [messages.length, loadingEarlierMessages])

    // #1252: the openai-agents / team blueprint first-use tips. The
    // openai-agents tip is itself an experimental affordance (#1230) and only
    // appears when that flag is on; the workspace-team tip is always available.
    const blueprintTipKind = useMemo<BlueprintTipKind | null>(() => {
      const kind = blueprintTipKindFor({
        teamId: teamFromUrl as string | null | undefined,
        agent: selectedAgent as any,
        blueprint: selectedBlueprint as any,
      })
      if (!kind) return null
      if (kind === 'openai-agents' && !isExperimentalFeatureEnabled('openai_agents')) {
        return null
      }
      return kind
    }, [teamFromUrl, selectedAgent, selectedBlueprint])
    const [blueprintTipDismissed, setBlueprintTipDismissed] = useState<boolean>(() =>
      blueprintTipKind ? isBlueprintTipDismissed(blueprintTipKind) : false,
    )
    useEffect(() => {
      if (!blueprintTipKind) {
        setBlueprintTipDismissed(false)
        return
      }
      setBlueprintTipDismissed(isBlueprintTipDismissed(blueprintTipKind))
      let cancelled = false
      void hydrateBlueprintTipsDismissed().then((bag) => {
        if (!cancelled && bag[blueprintTipKind]) setBlueprintTipDismissed(true)
      })
      return () => {
        cancelled = true
      }
    }, [blueprintTipKind])
    const handleBlueprintTipDismiss = (neverShowAgain: boolean) => {
      const kind = blueprintTipKind
      setBlueprintTipDismissed(true)
      if (kind) void persistBlueprintTipDismissed(kind, neverShowAgain)
    }

    // #1274: virtual timeline markers — derived from row ts at render time.
    // Day boundaries and same-day session resumes interleave into the display
    // list as virtual marker rows; they never enter the message list, so
    // edit/reaction turn indexing and compact/cull math are untouched.
    const displayItemsWithMarkers = useMemo(
      () =>
        interleaveTimelineMarkers(
          displayItems as any[],
          messages as Array<{ role: string; ts?: string | null }>,
        ),
      [displayItems, messages],
    )
    const markerNode = (marker: TimelineMarker, key: string) => (
      <p
        key={key}
        className="os-chat-status"
        data-role="status"
        data-testid="timeline-marker"
        data-marker-kind={marker.kind}
      >
        <span>{marker.label}</span>
      </p>
    )

    /* #1793 — one classification of the load state, so "no rows on screen" is
       never ambiguous between "still loading" and "your messages are gone".
         loading-empty → an explicit loading state (never a blank transcript)
         loading-stale → the rows on screen are a previous copy: dimmed,
                          aria-busy and inert, so no control inside is
                          clickable-but-confused
         error        → the refresh failed and the kept copy says so
         empty        → the fetch resolved with genuinely nothing
       The stale flag is applied to the ROWS THEMSELVES, not to a wrapper:
       wrapping them in an element that appears and disappears with the phase
       would unmount and remount every row on each transition (losing focus,
       scroll anchoring, and DOM identity). Each row keeps a stable parent, so
       the only change is an attribute plus a class. The status notice is a
       SIBLING of the rows, so it is never inside an `aria-busy` subtree and a
       screen reader announces it immediately. */
    const loadPhase = threadLoadPhase({
      threadReady: threadReady === true,
      messageCount: Array.isArray(messages) ? messages.length : 0,
      hydrateError,
    })
    const staleCopy = loadPhase === 'loading-stale'
    const staleCopyError = loadPhase === 'error' && (messages?.length ?? 0) > 0

    const rowsNode = (
      <>
      {displayItemsWithMarkers.map((item: any, idx: any) => {
            if (item.kind === 'marker') {
              // #1274: virtual timeline marker (day boundary / session resume).
              return markerNode(item.marker, item.key)
            }
            if (item.kind === 'summary') {
              if (hiddenSummaryIds.includes(item.summary.id)) return null
              return (
                <SummaryBlock
                  key={`sum-${item.summary.id}`}
                  summary={item.summary}
                  byId={summaryMap}
                  hiddenIds={hiddenSummaryIds}
                  onHide={(id: any) =>
                    setHiddenSummaryIds((prev: any) => (prev.includes(id) ? prev : [...prev, id]))
                  }
                  onToggleContext={handleToggleSummaryContext}
                  canEdit={messagesEditable}
                  onSaveEdit={handleSaveSummary}
                />
              )
            }
            const message = item.message
            if (hiddenMessageKeys.includes(message.key)) return null
            const liveMessage = messages.find((row: any) => row.key === message.key)
            const teammateTask = liveMessage?.teammateTask
            const subagentFanOut =
              liveMessage?.subagentFanOut ||
              ((teammateTask as any)?.subagents?.length
                ? (teammateTask as unknown as SubagentFanOutData)
                : undefined)
            if (subagentFanOut) {
              return (
                <div key={message.key} className="os-subagent-fan-out-wrap my-2">
                  <SubagentFanOutBlock event={subagentFanOut} />
                </div>
              )
            }
            if (teammateTask) {
              return (
                <div key={message.key} className="os-teammate-task-wrap my-2">
                  <TeammateTaskCard
                    event={teammateTask}
                    context={{
                      teamId: teamFromUrl,
                      team: selectedTeam,
                      remotes: configuredRemotes(remotesListQuery.data),
                    }}
                  />
                </div>
              )
            }
            const prOpened = liveMessage?.prOpened
            if (prOpened) {
              const openerId = prOpened.opener?.agentId
              const openerAgent = openerId
                ? blueprints.find((bp: any) => bp.id === openerId) ||
                  cliAgents.find((row: any) => row.id === openerId)
                : undefined
              const openerLabel =
                prOpened.opener?.name ||
                (openerAgent
                  ? editedAgentLabel({
                      id: openerId || '',
                      name: openerAgent.name || openerId,
                    })
                  : openerId)
              return (
                <div key={message.key} className="os-pr-opened-wrap my-2">
                  <PrOpenedCard
                    event={prOpened}
                    currentAgentId={activeChatAgentId}
                    currentConversationId={conversationId}
                    openerName={openerLabel}
                    openerAvatarSrc={(openerAgent as { avatar_path?: string } | undefined)?.avatar_path}
                    onJumpToOpener={jumpToPrOpener}
                  />
                </div>
              )
            }
            if (message.kind === 'prior_history') {
              const pill = (
                <SystemPreloadPill
                  key={message.key}
                  text={message.text}
                  label="Prior history"
                  onRemove={() =>
                    setHiddenMessageKeys((prev: any) =>
                      prev.includes(message.key) ? prev : [...prev, message.key],
                    )
                  }
                />
              )
              // #782: bubble-theme aware — IRC keeps the pill's disclosure but
              // seats it in the gutter grid so the vertical line stays whole.
              if (themeUsesIrcGutter(bubbleTheme)) {
                return (
                  <div key={message.key} className="os-irc-notice-row" data-testid="irc-notice-line">
                    <span
                      role="separator"
                      aria-orientation="vertical"
                      aria-label="Resize IRC name column"
                      className="os-irc-gutter-divider"
                      data-testid="irc-gutter-divider"
                    />
                    {pill}
                  </div>
                )
              }
              return pill
            }
            if (isStatusRole(message.role)) {
              const statusMs = parseCreatedAtMs(message.ts)
              // #1694: a hop that actually carried something is a boundary
              // marker, not a status line — the reader can open it and see the
              // context their next message was built on. Checked BEFORE the
              // rate-limit branch because a hop is never a rate-limit wait,
              // and before the generic status line so the announcement is not
              // rendered twice. The payload's PRESENCE is the discriminator:
              // the empty "No prior context to carry" branch never produces
              // one, so it falls through to the plain status line unchanged.
              if (CarriedSummaryBlock && message.carriedSummary) {
                return (
                  <CarriedSummaryBlock
                    key={message.key}
                    summary={message.carriedSummary}
                    notice={message.text}
                  />
                )
              }
              if (message.rateLimit) {
                // #782: rate-limit lines are bubble-theme aware — IRC renders
                // them as gutter lines; the settings click survives.
                const noticeSpec = getBubbleTheme(bubbleTheme).renderNoticeRow(
                  'System',
                  formatRateLimitNotice(message.rateLimit),
                  message.ts,
                  message.key,
                )
                if (noticeSpec.kind === 'gutter-line') {
                  const target =
                    message.rateLimit.settings ||
                    settingsTargetForProvider(message.rateLimit.provider)
                  return (
                    <IrcNoticeLine
                      key={message.key}
                      speaker={noticeSpec.speaker}
                      text={noticeSpec.text}
                      ts={noticeSpec.ts}
                      rowKey={noticeSpec.key}
                      onClick={() =>
                        openSettingsSheet({
                          section: target.section,
                          providerId: target.provider_id,
                          focusRateLimits: true,
                        })
                      }
                    />
                  )
                }
                return (
                  <RateLimitStatusLine
                    key={message.key}
                    wait={message.rateLimit}
                    nowMs={nowMs}
                    ts={message.ts}
                    timeLabel={statusMs != null ? formatGapLabel(statusMs) : undefined}
                  />
                )
              }
              // #782: notice rows follow the bubble theme — IRC renders them
              // as `<System> message` gutter lines so the transcript column
              // stays whole; every other theme keeps the legacy status line.
              const noticeSpec = getBubbleTheme(bubbleTheme).renderNoticeRow(
                'System',
                message.text,
                message.ts,
                message.key,
              )
              if (noticeSpec.kind === 'gutter-line') {
                return (
                  <IrcNoticeLine
                    key={message.key}
                    speaker={noticeSpec.speaker}
                    text={noticeSpec.text}
                    ts={noticeSpec.ts}
                    rowKey={noticeSpec.key}
                  />
                )
              }
              return (
                <p
                  key={message.key}
                  className="os-chat-status"
                  data-role="status"
                  data-testid="chat-status"
                  data-ts={message.ts || undefined}
                >
                  <span>{message.text}</span>
                  {statusMs != null ? (
                    <time dateTime={message.ts} data-testid="chat-status-time">
                      {formatGapLabel(statusMs)}
                    </time>
                  ) : null}
                </p>
              )
            }
            const isLast = idx === displayItems.length - 1
            const retryEnabled =
              SHOW_MESSAGE_ACTIONS &&
              isLast &&
              message.role === 'assistant' &&
              !message.streaming &&
              lastUserTextRef.current.length > 0
            const messageIndex = messages.findIndex((row: any) => row.key === message.key)
            const canEditThis =
              messagesEditable &&
              !message.streaming &&
              (message.role === 'user' || message.role === 'assistant')
            const canCompressThis =
              (isApiAgent || agentKind === 'blueprint') &&
              !message.streaming &&
              (message.role === 'user' || message.role === 'assistant') &&
              rawOffsetForMessage(messages, message.key) >= 0
            const showRowActions =
              !message.streaming &&
              editingKey !== message.key &&
              (message.role === 'user' || message.role === 'assistant') &&
              (Boolean(message.text.trim()) || retryEnabled || canEditThis || canCompressThis)
            // #505 / REQ-907: IRC overlays the action row onto the bubble line.
            // Overlay is hover-scoped in CSS; below md the row stays in flow so
            // touch devices never permanently cover message text.
            const rowOverlay =
              getBubbleTheme(bubbleTheme).actionRowPlacement === 'overlay' && !message.streaming
            // #1684: indicator (a) — "waiting on a model response". Unchanged,
            // and deliberately NOT the same source the badge reads.
            const isStreamingAssistant = message.role === 'assistant' && Boolean(message.streaming)
            const bubbleAvatar =
              message.role === 'assistant' ? (
                isStreamingAssistant ? (
                  // Hover target (a) for the stop reveal. The handlers are on
                  // the same `os-composer-working` slot the eye-dots already
                  // live in — no new wrapper, no parallel CSS rule: the state
                  // they set ends up as the badge's own `--revealed` class.
                  <div
                    className="os-composer-working os-inline-working"
                    data-testid="composer-working-indicator"
                    role="status"
                    aria-live="polite"
                    aria-label={workingTip}
                    onMouseEnter={revealRow.bind(null, message.key)}
                    onPointerEnter={revealRow.bind(null, message.key)}
                    onMouseLeave={concealRow.bind(null, message.key)}
                    onPointerLeave={concealRow.bind(null, message.key)}
                  >
                    <span
                      className="tooltip tooltip-right os-composer-working__tip"
                      data-tip={workingTip}
                    >
                      <span className="os-composer-working__avatar os-inline-working__avatar">
                        <AgentAvatar
                          src={selectedAgent?.avatar_path}
                          agentId={teamFromUrl || agentIdFromBlueprint(selectedBlueprint)}
                          active={true}
                          status="working"
                          size="xs"
                          className="shrink-0"
                        />
                      </span>
                    </span>
                  </div>
                ) : (
                  <AgentAvatar
                    src={selectedAgent?.avatar_path}
                    agentId={teamFromUrl || agentIdFromBlueprint(selectedBlueprint)}
                    active={false}
                    status="idle"
                    size="xs"
                    className="shrink-0"
                  />
                )
              ) : undefined
            const rawOffset = rawOffsetForMessage(messages, message.key)
            const showStartMarker =
              contextMeta.start_offset > 0 && rawOffset === contextMeta.start_offset
            const rowPersona =
              message.role === 'assistant'
                ? personaForAgentMessage(message, selectedAgent?.personas)
                : null
            const parsedArtifacts = extractThinkingBlock(message.text)
            const hasThinking = Boolean(parsedArtifacts.thinking)
            const thinkingOpen = expandedThinkingKeys.has(message.key)
            const isHerdrMessage = isHerdrSeat || Boolean(message.rawResponse)
            // #1793: while the thread is still loading, this row is the CACHED
            // copy — `os-thread-stale` greys it, `aria-busy` tells AT the
            // content is not final, and `inert` makes every control inside
            // non-focusable and non-clickable. Applied to the ROW itself so no
            // wrapper appears/disappears with the phase and the row subtree is
            // never remounted.
            const rowClass = staleCopy
              ? 'group/osrow group/running os-chat-row os-thread-stale'
              : 'group/osrow group/running os-chat-row'
            return (
              <div
                key={message.key}
                data-message-key={message.key}
                data-persona={rowPersona ?? undefined}
                className={rowClass}
                {...(staleCopy
                  ? {
                      'aria-busy': 'true',
                      'data-stale-copy': 'true',
                      inert: '' as unknown as boolean,
                    }
                  : {})}
                onContextMenu={(e) => {
                  if (message.role === 'system') return
                  if (staleCopy) return
                  handleBubbleContextMenu(e, message)
                }}
                onMouseUp={(e) => {
                  // #846: remember what was highlighted in THIS row before any
                  // right-click can collapse the selection.
                  if (message.role === 'system') return
                  cacheRowSelection(message.key, e.currentTarget)
                }}
                onMouseDown={(e) => {
                  if (message.role === 'system') return
                  if (e.button === 2) {
                    // #846: stop the right-click from wiping the selection
                    // before the context menu can read it.
                    e.preventDefault()
                  }
                }}
              >
                {newBeforeKey === message.key ? <ChatNewRule /> : null}
                {showStartMarker ? (
                  <div
                    className="my-2 flex items-center gap-2 text-[11px] uppercase tracking-wide text-base-content/50"
                    data-testid="context-starts-here"
                    role="separator"
                    aria-label={START_CONTEXT_FROM_HERE_LABEL}
                  >
                    <span className="h-px flex-1 bg-base-300" />
                    <span>{START_CONTEXT_FROM_HERE_LABEL}</span>
                    <span className="h-px flex-1 bg-base-300" />
                  </div>
                ) : null}
                <ChatMessageBubble
                  theme={bubbleTheme}
                  role={message.role}
                  agentName={selectedAgentName}
                  text={message.reactionOnly ? '' : message.text}
                  reactionOnly={Boolean(message.reactionOnly)}
                  streaming={message.streaming}
                  seatId={activeChatAgentId}
                  edited={message.edited}
                  ts={message.ts}
                  avatar={bubbleAvatar}
                  skillCatalog={skillCatalog}
                  sendFailed={message.sendFailed}
                  onResend={() => onResendSend?.(message.key, message.text)}
                  onOpenSkill={setOpenSkillName}
                  thinkingOpen={thinkingOpen}
                  onToggleThinking={() => toggleThinking(message.key)}
                  isHerdr={isHerdrMessage}
                  onRemoveCard={() =>
                    setHiddenMessageKeys((prev: any) =>
                      prev.includes(message.key) ? prev : [...prev, message.key],
                    )
                  }
                  editing={editingKey === message.key}
                  onCancelEdit={() => setEditingKey(null)}
                  onSaveEdit={(next: any) => {
                    if (messageIndex >= 0) void saveEditedMessage(messageIndex, next)
                  }}
                >
                  {message.reactionOnly ? (
                    <MessageReactionPills
                      alwaysVisible
                      reactions={message.reactions ?? []}
                      onToggle={(emoji: string) => {
                        if (messageIndex >= 0) toggleMessageReaction?.(messageIndex, emoji)
                      }}
                    />
                  ) : null}
                  {message.subagentFanOut ? (
                    <div className="my-2">
                      <SubagentFanOutBlock event={message.subagentFanOut} />
                    </div>
                  ) : null}
                  {(message.tools ?? []).map((tool: any) => (
                    <ToolCallPopup
                      key={tool.id}
                      tool={tool}
                      hideRunningBadge={
                        Boolean(activeToolName) &&
                        String(tool?.name || '') === String(activeToolName)
                      }
                      onDecision={(decision: any) => {
                        const agentId = tool.agentId || selectedBlueprint || threadKey
                        if (decision === 'always') rememberAlwaysAllow(agentId, tool.name)
                        sendToolDecision(tool.id, decision)
                        attachToolToThread({
                          ...tool,
                          needsApproval: false,
                          status:
                            decision === 'deny'
                              ? 'denied'
                              : decision === 'always' || decision === 'allow'
                                ? 'allowed'
                                : tool.status,
                        })
                      }}
                    />
                  ))}
                  {message.question ? (
                    <QuestionCard
                      question={message.question}
                      disabled={
                        message.questionAnswered === true ||
                        (message.tools ?? []).some((tool: any) => tool.needsApproval)
                      }
                      onChoose={(value: any) => {
                        if (message.questionBlocking) {
                          sendQuestionAnswer(message.question!.id, value)
                        } else {
                          sendText(value)
                        }
                        setThreads((prev: any) => {
                          const current = prev[threadKey] ?? []
                          return {
                            ...prev,
                            [threadKey]: current.map((row: any) =>
                              row.key === message.key
                                ? { ...row, questionAnswered: true }
                                : row,
                            ),
                          }
                        })
                      }}
                    />
                  ) : null}
                </ChatMessageBubble>
                {/* #1096: the per-agent stop tracks the END of the streaming
                    message — it renders AFTER the bubble content, not beside
                    the avatar. Clicking interrupts this agent's turn; other
                    turns keep streaming (per-agent interrupt, #1097 seam). */}
                {/* #1684: the stop slot is mounted for a streaming assistant
                    row — that is the "this turn is live" contract, unchanged
                    from #1371 — but the BADGE inside it is now the
                    tool-in-flight signal, not a second view of `streaming`. A
                    plain streaming turn therefore shows eye-dots only, and a
                    tool call shows the badge. */}
                {isStreamingAssistant && interruptRunningTurn ? (
                  <div
                    className={`mt-1 flex justify-start os-agent-row__stop-slot os-agent-row__stop-slot--${
                      getBubbleTheme(bubbleTheme).messageLayout === 'line' ? 'line' : 'bubble'
                    }`}
                    data-stop-axis={
                      getBubbleTheme(bubbleTheme).messageLayout === 'line' ? 'line' : 'bubble'
                    }
                    data-testid="agent-row-stop-slot"
                  >
                    {/* #1371: the badge slot is the standing chrome; Stop
                        reveals on hover of EITHER working indicator (the
                        eye-dots above, or this badge). Click still interrupts
                        this agent's turn (#1096 / #1097). */}
                    <RunningStopBadge
                      onStop={() => interruptRunningTurn()}
                      toolName={activeToolName}
                      revealedExternally={revealKey === message.key}
                    />
                  </div>
                ) : null}
                {message.reactionOnly ? null : (
                <MessageReactionPills
                  reactions={message.reactions ?? []}
                  onToggle={(emoji: string) => {
                    if (messageIndex >= 0) toggleMessageReaction?.(messageIndex, emoji)
                  }}
                />
                )}
                {showRowActions ? (
                  <MessageRowActions
                    text={message.text}
                    overlay={rowOverlay}
                    onAddReaction={
                      messageIndex >= 0
                        ? (emoji: string) => toggleMessageReaction?.(messageIndex, emoji)
                        : undefined
                    }
                    reactionEmojis={
                      typeof getBubbleTheme === 'function'
                        ? getBubbleTheme(bubbleTheme)?.reactionEmojis?.()
                        : undefined
                    }
                    canEdit={canEditThis}
                    onStartEdit={() => setEditingKey(message.key)}
                    canCompress={canCompressThis}
                    contextStrategy={contextStrategy}
                    hasThinking={hasThinking}
                    thinkingOpen={thinkingOpen}
                    onToggleThinking={() => toggleThinking(message.key)}
                    isHerdr={isHerdrMessage}
                    rawResponse={message.rawResponse || (isHerdrMessage ? message.text : undefined)}
                    onShowRawResponse={() => setRawResponseModalText(message.rawResponse || message.text)}
                    onCompressToHere={() => {
                      handleContextToHere(message)
                    }}
                    onReply={() => {
                      // #846: row-action Reply honors a scoped selection in
                      // this bubble too — not just the context menu.
                      const row = document.querySelector<HTMLDivElement>(
                        `[data-message-key="${CSS.escape(message.key)}"]`,
                      )
                      const quoted =
                        resolveReplyQuote({
                          targetElement: row,
                          cached: activeSelectionRef.current,
                          messageKey: message.key,
                        }) || message.text
                      setReplyTarget({
                        key: message.key,
                        role: message.role,
                        speaker:
                          message.role === 'user' ? 'You' : selectedAgentName,
                        text: quoted,
                      })
                      composerRef.current?.focus()
                    }}
                    className={message.role === 'user' ? 'w-full justify-end' : undefined}
                  >
                    {message.role === 'assistant' && message.text.trim() ? (
                      <ReadAloudButton
                        text={message.text}
                        agentId={activeChatAgentId}
                        bind={voiceBind}
                      />
                    ) : null}
                    {message.role === 'assistant' && SHOW_MESSAGE_ACTIONS && (
                      <ChatMessageActions
                        text={message.text}
                        onRetry={
                          retryEnabled
                            ? () => {
                                sendText(lastUserTextRef.current)
                              }
                            : undefined
                        }
                      />
                    )}
                  </MessageRowActions>
                ) : null}
              </div>
            )
          })}
      </>
    )

    return (
        <div
          className="os-chat-messages space-y-1 flex-1"
          data-testid="chat-messages-container"
          data-load-phase={loadPhase}
        >
        {staleCopy ? (
          <p
            className="os-thread-load-notice"
            data-testid="chat-thread-stale-status"
            role="status"
            aria-live="polite"
            aria-atomic="true"
          >
            <span className="loading loading-spinner loading-xs" aria-hidden="true" />
            <span>{THREAD_STALE_LABEL}</span>
          </p>
        ) : null}
        {staleCopyError ? (
          <p
            className="os-thread-load-notice os-thread-load-notice--error"
            data-testid="chat-thread-stale-error"
            role="alert"
          >
            <span>
              Could not refresh this conversation — showing the copy already on screen.
              {hydrateError ? ` ${hydrateError}` : ''}
            </span>
          </p>
        ) : null}
        {loadPhase === 'loading-empty' ? (
          <div
            className="flex h-full min-h-64 flex-col items-center justify-center gap-3 text-center text-base-content/45"
            data-testid="chat-thread-loading"
            role="status"
            aria-live="polite"
            aria-atomic="true"
          >
            <span className="loading loading-spinner loading-md" aria-hidden="true" />
            <p className="text-sm">{THREAD_LOADING_LABEL}…</p>
          </div>
        ) : null}
        {hasEarlierMessages ? (
          <div className="flex w-full justify-center py-2">
            <button
              type="button"
              className="btn btn-ghost btn-xs"
              data-testid="load-earlier-messages"
              // #1793: a control inside the dimmed copy is DISABLED, not
              // clickable-but-confused — the page it would fetch is not the
              // one on screen.
              disabled={loadingEarlierMessages || staleCopy}
              aria-busy={loadingEarlierMessages || staleCopy}
              onClick={handleLoadEarlier}
            >
              {loadingEarlierMessages ? 'Loading earlier messages…' : 'Load earlier messages'}
            </button>
          </div>
        ) : null}
        {blueprintTipKind && !blueprintTipDismissed ? (
          <BlueprintTip kind={blueprintTipKind} onDismiss={handleBlueprintTipDismiss} />
        ) : null}
        {restoreNotice ? (
          <p className="os-chat-status" data-role="status" data-testid="chat-status">
            <span>{restoreNotice}</span>
          </p>
        ) : null}
        {loadPhase === 'error' && (messages?.length ?? 0) === 0 ? (
          <div
            className="flex h-full min-h-64 flex-col items-center justify-center gap-3 text-center text-base-content/70"
            data-testid="chat-hydrate-error"
            role="alert"
          >
            <p className="text-sm font-medium">Could not load this chat</p>
            <p className="max-w-sm text-xs text-base-content/50">{hydrateError}</p>
          </div>
        ) : loadPhase === 'empty' ? (
          <div className="flex h-full min-h-64 flex-col items-center justify-center gap-3 text-center text-base-content/45">
            <p className="text-sm">Message {selectedAgentName}</p>
            {demoMode ? (
              <DemoTourBanner disabled={chipsDisabled} onChoose={chooseSuggestion} />
            ) : showGettingStartedFlow && gettingStartedFlow ? (
              <>
                <p
                  className="max-w-sm text-xs text-base-content/50"
                  data-testid="getting-started-flow"
                >
                  First chat applies getting-started skill{' '}
                  <span className="font-medium text-base-content/70">
                    {gettingStartedFlow.skill}
                  </span>
                  . When to use: {gettingStartedFlow.whenToUse}
                </p>
                <SuggestionChips
                  chips={gettingStartedChips}
                  disabled={chipsDisabled}
                  onChoose={chooseSuggestion}
                />
              </>
            ) : showSupportJourneyChips ? (
              <>
                <p className="max-w-sm text-xs text-base-content/50">
                  Start with a team, a remote, or a CLI — one pane, no Settings maze.
                </p>
                <SuggestionChips
                  chips={supportJourneyChips}
                  disabled={chipsDisabled}
                  onChoose={chooseSuggestion}
                />
              </>
            ) : null}
          </div>
        ) : (messages?.length ?? 0) === 0 ? null : (
          rowsNode
        )}
        {showCliSessionRecovery ? (
          <CliSessionRecoveryBanner
            onStartFresh={startFreshCliSession}
            onRetry={retryCliSession}
            onClearHistory={clearCliSessionHistory}
            configTarget={cliRecoveryConfigTarget}
            onConfigure={(target: any) => openSettingsSheet({ section: target.section })}
          />
        ) : null}
        {fanOutCards.length > 0 ? (
          <div
            className="os-running-card-stack"
            data-testid="running-card-stack"
            role="status"
            aria-live="polite"
            aria-label="Running agents"
          >
            {fanOutCards.map((card) => (
              <RunningCard
                key={card.key}
                legId={card.legId}
                name={card.name}
                badge={card.badge}
                status={card.status}
                live={card.live}
                href={card.href}
                external={card.external}
                onStop={stopLeg}
              />
            ))}
          </div>
        ) : null}
        {awaitingAssistant && !streamingMessage && fanOutCards.length === 0 && (
          <div
            className="os-chat-message os-chat-message--assistant group/osrow flex flex-col gap-1 items-start my-2"
            role="status"
            aria-live="polite"
            aria-label={workingTip}
          >
            <div className="group/running flex items-center gap-2.5 py-1 px-1" data-testid="agent-row-running">
              {/* #1684: same split as the streaming row — the eye-dots are
                  "waiting on a model response", the badge is "a tool call is
                  in flight". This standalone row is the awaiting-first-token
                  state, so it is dominated by the eye-dots and only badges
                  when the phase signal says a tool is actually running. */}
              <div
                className="os-composer-working os-inline-working"
                data-testid="composer-working-indicator"
                role="status"
                aria-live="polite"
                aria-label={workingTip}
                onMouseEnter={revealRow.bind(null, AWAITING_ROW_KEY)}
                onPointerEnter={revealRow.bind(null, AWAITING_ROW_KEY)}
                onMouseLeave={concealRow.bind(null, AWAITING_ROW_KEY)}
                onPointerLeave={concealRow.bind(null, AWAITING_ROW_KEY)}
              >
                <span className="tooltip tooltip-right os-composer-working__tip" data-tip={workingTip}>
                  <span className="os-composer-working__avatar os-inline-working__avatar">
                    <AgentAvatar
                      src={selectedAgent?.avatar_path}
                      agentId={teamFromUrl || agentIdFromBlueprint(selectedBlueprint)}
                      active={true}
                      status="working"
                      size="xs"
                      className="shrink-0"
                    />
                  </span>
                </span>
              </div>
              {/* #1371: the badge slot hosts the stop control, revealed on
                  hover of EITHER indicator (#1684). Composer stays
                  submit-only (#1096). */}
              {interruptRunningTurn ? (
                <RunningStopBadge
                  onStop={() => interruptRunningTurn()}
                  toolName={activeToolName}
                  revealedExternally={revealKey === AWAITING_ROW_KEY}
                />
              ) : null}
            </div>
          </div>
        )}
        <div ref={listEndRef} />
        </div>

    )
  },
)

export default ChatMessageList
