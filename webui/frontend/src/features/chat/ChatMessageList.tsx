/**
 * #856 slice F — the chat message list, moved verbatim from ChatPage.tsx.
 *
 * Renders the scrollable message surface: restore/hydrate states, empty
 * states (demo + support journeys), the summary/message/fan-out row loop
 * with per-row actions, the CLI recovery banner, the inline working
 * indicator, and the scroll-anchor. ChatPage owns all state and passes it
 * down as one props object.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- pass-through props during extraction
import { forwardRef } from 'react'
import type { SubagentFanOutData } from '../../lib/subagentFanOut'

export interface ChatMessageListProps {
  [key: string]: any
}

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
    skillCatalog,
    startFreshCliSession,
    streamingMessage,
    summaryMap,
    supportJourneyChips,
    teamFromUrl,
    themeUsesIrcGutter,
    threadKey,
    threadReady,
    toggleThinking,
    voiceBind,
    workingTip,
    interruptRunningTurn,
  } = props as Record<string, any>

    return (
        <div className="os-chat-messages space-y-1 flex-1" data-testid="chat-messages-container">
        {restoreNotice ? (
          <p className="os-chat-status" data-role="status" data-testid="chat-status">
            <span>{restoreNotice}</span>
          </p>
        ) : null}
        {messages.length === 0 && threadReady && hydrateError ? (
          <div
            className="flex h-full min-h-64 flex-col items-center justify-center gap-3 text-center text-base-content/70"
            data-testid="chat-hydrate-error"
            role="alert"
          >
            <p className="text-sm font-medium">Could not load this chat</p>
            <p className="max-w-sm text-xs text-base-content/50">{hydrateError}</p>
          </div>
        ) : messages.length === 0 && threadReady ? (
          <div className="flex h-full min-h-64 flex-col items-center justify-center gap-3 text-center text-base-content/45">
            <p className="text-sm">Message {selectedAgentName}</p>
            {demoMode ? (
              <DemoTourBanner disabled={chipsDisabled} onChoose={chooseSuggestion} />
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
        ) : messages.length === 0 ? null : (
          <>
          {displayItems.map((item: any, idx: any) => {
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
            const isStreamingAssistant = message.role === 'assistant' && Boolean(message.streaming)
            const bubbleAvatar =
              message.role === 'assistant' ? (
                isStreamingAssistant ? (
                  <>
                  <div
                    className="os-composer-working os-inline-working"
                    data-testid="composer-working-indicator"
                    role="status"
                    aria-live="polite"
                    aria-label={workingTip}
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
                  {/* #1096: per-agent stop beside the streaming avatar. */}
                  {interruptRunningTurn ? (
                    <button
                      type="button"
                      className="os-agent-row__stop"
                      aria-label="Stop generating"
                      title="Stop this agent's generation (other turns keep running)"
                      data-testid="agent-row-stop"
                      onClick={() => interruptRunningTurn()}
                    >
                      <svg viewBox="0 0 16 16" className="h-3 w-3 fill-current" aria-hidden="true" focusable="false">
                        <rect x="3" y="3" width="10" height="10" rx="1.5" />
                      </svg>
                    </button>
                  ) : null}
                  </>
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
            return (
              <div
                key={message.key}
                data-message-key={message.key}
                data-persona={rowPersona ?? undefined}
                className="group/osrow os-chat-row"
                onContextMenu={(e) => {
                  if (message.role === 'system') return
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
                  text={message.text}
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
                  {message.subagentFanOut ? (
                    <div className="my-2">
                      <SubagentFanOutBlock event={message.subagentFanOut} />
                    </div>
                  ) : null}
                  {(message.tools ?? []).map((tool: any) => (
                    <ToolCallPopup
                      key={tool.id}
                      tool={tool}
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
                {showRowActions ? (
                  <MessageRowActions
                    text={message.text}
                    overlay={rowOverlay}
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
        {awaitingAssistant && !streamingMessage && (
          <div
            className="os-chat-message os-chat-message--assistant group/osrow flex flex-col gap-1 items-start my-2"
            role="status"
            aria-live="polite"
            aria-label={workingTip}
          >
            <div className="flex items-center gap-2.5 py-1 px-1">
              <div
                className="os-composer-working os-inline-working"
                data-testid="composer-working-indicator"
                role="status"
                aria-live="polite"
                aria-label={workingTip}
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
              <span className="inline-flex items-center gap-2 text-xs text-base-content/70 italic">
                <span>{workingTip || 'Thinking…'}</span>
                <span className="loading loading-dots loading-xs opacity-70" />
              </span>
              {/* #1096: the stop affordance lives HERE — on the generating
                  agent's transcript row, beside its animated avatar — not in
                  the composer. Clicking interrupts this agent's turn; other
                  turns keep streaming (per-agent interrupt, #1097 seam). */}
              {interruptRunningTurn ? (
                <button
                  type="button"
                  className="os-agent-row__stop"
                  aria-label="Stop generating"
                  title="Stop this agent's generation (other turns keep running)"
                  data-testid="agent-row-stop"
                  onClick={() => interruptRunningTurn()}
                >
                  <svg
                    viewBox="0 0 16 16"
                    className="h-3 w-3 fill-current"
                    aria-hidden="true"
                    focusable="false"
                  >
                    <rect x="3" y="3" width="10" height="10" rx="1.5" />
                  </svg>
                </button>
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
