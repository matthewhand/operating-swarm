/**
 * #856 slice L — ChatPage's overlay cluster, moved verbatim: the message
 * context menu (Reply/Copy/compress-to-here), TokenDiagnosticsModal,
 * SkillPopup, RawResponseModal, start-from-here ConfirmModal,
 * GenerationsPanel, and SessionPicker. Pure presentation — ChatPage keeps
 * the state and passes it as props.
 */
import type * as React from 'react'

type Props = Record<string, any>

export function ChatOverlays(props: Props): React.ReactNode {
  const {
    COPY_EMPTY_MESSAGE,
    COPY_EMPTY_TITLE,
    COPY_FAILED_MESSAGE,
    COPY_FAILED_TITLE,
    ConfirmModal,
    Copy,
    FoldVertical,
    GenerationsPanel,
    RawResponseModal,
    Reply,
    START_CONTEXT_FROM_HERE_LABEL,
    START_CONTEXT_FROM_HERE_TOOLTIP,
    SessionPicker,
    SkillPopup,
    TokenDiagnosticsModal,
    agentKind,
    applyStartFromHere,
    assistantMessageCount,
    composerRef,
    contextMax,
    contextMenu,
    contextMeta,
    contextStrategy,
    conversationId,
    copyTextToClipboard,
    generationContexts,
    generationsOpen,
    handleContextToHere,
    headerFaceAgentId,
    inputTokens,
    isApiAgent,
    messages,
    openSkillName,
    outputTokens,
    rawResponseModalText,
    remoteFromUrl,
    remoteThreadPicker,
    seatToolCalls,
    selectedAgentName,
    setContextMenu,
    setGenerationsOpen,
    setOpenSkillName,
    setRawResponseModalText,
    setRemoteThreadPicker,
    setReplyTarget,
    setSearchParams,
    setStartFromHereWarning,
    setTokenDiagOpen,
    skillCatalog,
    startFromHereWarning,
    summaries,
    toastError,
    tokenCount,
    tokenDiagOpen,
    toolCallsCount,
    userMessageCount,
} = props

  return (
    <>

      {contextMenu && (
        <>
          <div
            className="fixed inset-0 z-40"
            data-testid="context-menu-backdrop"
            onClick={() => setContextMenu(null)}
            onContextMenu={(e) => {
              e.preventDefault()
              setContextMenu(null)
            }}
          />
          <div
            role="menu"
            aria-label="Message actions"
            data-testid="message-context-menu"
            className="fixed z-50 min-w-32 rounded-lg border border-base-300 bg-base-100 p-1 shadow-xl text-sm"
            style={{
              left: `${Math.min(contextMenu.x, typeof window !== 'undefined' ? window.innerWidth - 150 : 0)}px`,
              top: `${Math.min(contextMenu.y, typeof window !== 'undefined' ? window.innerHeight - 80 : 0)}px`,
            }}
          >
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded px-3 py-1.5 text-left text-sm hover:bg-base-200 cursor-pointer"
              data-testid="context-menu-reply"
              onClick={() => {
                setReplyTarget({
                  key: contextMenu.message.key,
                  role: contextMenu.message.role,
                  speaker:
                    contextMenu.message.role === 'user' ? 'You' : selectedAgentName,
                  text: contextMenu.selectedText || contextMenu.message.text,
                })
                setContextMenu(null)
                composerRef.current?.focus()
              }}
            >
              <Reply className="h-4 w-4 opacity-70" aria-hidden="true" />
              {/* #846: label names the target — a partial selection is a quote. */}
              {contextMenu.selectedText ? 'Reply to quote' : 'Reply'}
            </button>
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded px-3 py-1.5 text-left text-sm hover:bg-base-200 cursor-pointer"
              data-testid="context-menu-copy"
              onClick={() => {
                const textToCopy = contextMenu.selectedText || contextMenu.message.text
                setContextMenu(null)
                void copyTextToClipboard(textToCopy).then((result: string) => {
                  if (result === 'empty') {
                    toastError(COPY_EMPTY_TITLE, COPY_EMPTY_MESSAGE)
                  } else if (result === 'failed') {
                    toastError(COPY_FAILED_TITLE, COPY_FAILED_MESSAGE)
                  }
                })
              }}
            >
              <Copy className="h-4 w-4 opacity-70" aria-hidden="true" />
              {contextMenu.selectedText ? 'Copy selection' : 'Copy'}
            </button>
            {(isApiAgent || agentKind === 'blueprint') &&
            (contextMenu.message.role === 'user' || contextMenu.message.role === 'assistant') &&
            !contextMenu.message.streaming ? (
              <button
                type="button"
                role="menuitem"
                className="flex w-full items-center gap-2 rounded px-3 py-1.5 text-left text-sm hover:bg-base-200 cursor-pointer"
                data-testid={
                  contextStrategy === 'cull'
                    ? 'context-menu-start-from-here'
                    : 'context-menu-compress-to-here'
                }
                title={
                  contextStrategy === 'cull' ? START_CONTEXT_FROM_HERE_TOOLTIP : 'Compress to here'
                }
                onClick={() => {
                  handleContextToHere(contextMenu.message)
                }}
              >
                <FoldVertical className="h-4 w-4 opacity-70" aria-hidden="true" />
                {contextStrategy === 'cull' ? START_CONTEXT_FROM_HERE_LABEL : 'Compress to here'}
              </button>
            ) : null}
            {/* #724: the bubble-theme picker moved to the rail agent
                right-click menu — presentation is an agent-level choice, not
                a message-level action. */}
          </div>
        </>
      )}

      <TokenDiagnosticsModal
        isOpen={tokenDiagOpen}
        onClose={() => setTokenDiagOpen(false)}
        agentName={selectedAgentName}
        conversationId={conversationId}
        tokenCount={tokenCount}
        contextMax={contextMax}
        inputTokens={inputTokens}
        outputTokens={outputTokens}
        compactsCount={summaries.length}
        toolCallsCount={toolCallsCount}
        messageCount={messages.length}
        userMessageCount={userMessageCount}
        assistantMessageCount={assistantMessageCount}
        contextStrategy={contextStrategy}
        lastContextEvent={contextMeta.last_event}
      />

      <SkillPopup
        name={openSkillName}
        open={openSkillName != null}
        onClose={() => setOpenSkillName(null)}
        catalog={skillCatalog}
      />

      <RawResponseModal
        isOpen={rawResponseModalText !== null}
        onClose={() => setRawResponseModalText(null)}
        text={rawResponseModalText ?? ''}
      />

      <ConfirmModal
        isOpen={startFromHereWarning != null}
        onClose={() => setStartFromHereWarning(null)}
        onConfirm={async () => {
          const pending = startFromHereWarning
          if (!pending) return
          await applyStartFromHere(pending.message, true)
        }}
        title={START_CONTEXT_FROM_HERE_LABEL}
        confirmText="Confirm"
        cancelText="Cancel"
        confirmVariant="warning"
        aria-label="Start context from here warning"
      >
        <p className="text-sm" data-testid="start-from-here-warning">
          {startFromHereWarning?.copy}
        </p>
      </ConfirmModal>

      <GenerationsPanel
        open={generationsOpen}
        onClose={() => setGenerationsOpen(false)}
        agentId={headerFaceAgentId}
        agentName={selectedAgentName || 'Agent'}
        contexts={generationContexts}
        activeContextId={conversationId}
        onSwitchContext={() => {
          /* Single-context today; multi-context switching lands with session history UI. */
        }}
        toolCalls={seatToolCalls}
      />


      <SessionPicker
        open={remoteThreadPicker !== null}
        title={remoteFromUrl || 'Remote'}
        sessions={remoteThreadPicker ?? []}
        onClose={() => setRemoteThreadPicker(null)}
        onSelect={(session: any) => {
          const resumeId = String(session.memberId || session.id || '').trim()
          if (!resumeId || !remoteFromUrl) return
          setSearchParams(
            (prev: URLSearchParams) => {
              const next = new URLSearchParams(prev)
              next.set('remote', remoteFromUrl)
              next.set('session', resumeId)
              return next
            },
            { replace: true },
          )
          setRemoteThreadPicker(null)
        }}
      />
    </>
  )
}
