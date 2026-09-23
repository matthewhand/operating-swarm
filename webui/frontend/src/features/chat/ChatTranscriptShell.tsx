/**
 * #856 slice M - ChatPage's transcript shell, moved verbatim: the tips pills
 * row, the sr-only connection status line, and the os-chat-transcript
 * container (#445 clip contract, #857 composer inset, IRC gutter rail) with
 * the message list and bottom dock slots. Pure structure - ChatPage keeps
 * the state.
 */
import type * as React from 'react'
import type { CSSProperties } from 'react'

type Props = Record<string, any>

export function ChatTranscriptShell(props: Props): React.ReactNode {
  const {
    ChatBottomDock,
    ChatMessageList,
    ConsumerPills,
    DefaultLlmTip,
    RoleAgentTip,
    activeChatAgentId,
    agentKind,
    bubbleTheme,
    chatBottomDockProps,
    chatMessageListProps,
    composerInsetCustomProperty,
    composerInsetPx,
    dismissDefaultLlmTip,
    dismissRoleTip,
    getBubbleTheme,
    handleTranscriptScroll,
    ircGutterDragging,
    ircGutterPx,
    isCliAgent,
    isRemoteAgent,
    messagesEditable,
    onIrcRailDoubleClick,
    onIrcRailPointerDown,
    onIrcRailPointerMove,
    onIrcRailPointerUp,
    remoteFromUrl,
    scrollBoxRef,
    showDefaultLlmTip,
    showRoleTip,
    statusLabel,
    themeUsesIrcGutter,
} = props

  return (
    <>
      <ConsumerPills providerId={activeChatAgentId} />
      {showRoleTip ? <RoleAgentTip onDismiss={dismissRoleTip} /> : null}
      {showDefaultLlmTip ? <DefaultLlmTip onDismiss={dismissDefaultLlmTip} /> : null}

      <span role="status" aria-live="polite" aria-atomic="true" aria-label="Connection status" className="sr-only">
        {statusLabel}
      </span>

      <div
        ref={scrollBoxRef}
        className="os-chat-transcript min-h-0 flex-1 space-y-1 overflow-y-auto px-2 py-3 sm:px-3 select-none outline-none focus:outline-none flex flex-col justify-between relative"
        data-composer-inset={composerInsetPx}
        data-bubble-theme={bubbleTheme}
        style={
          {
            ...((composerInsetCustomProperty(composerInsetPx) as CSSProperties) ?? {}),
            ...(themeUsesIrcGutter(bubbleTheme)
              ? ({ ['--irc-gutter-px' as string]: `${ircGutterPx}px` } as React.CSSProperties)
              : {}),
          } as React.CSSProperties
        }
        data-message-layout={getBubbleTheme(bubbleTheme).messageLayout}
        aria-live="polite"
        role="log"
        aria-label="Conversation"
        data-agent-kind={
          remoteFromUrl || isRemoteAgent || agentKind === 'remote'
            ? 'remote'
            : isCliAgent
              ? 'cli'
              : agentKind
        }
        data-messages-editable={messagesEditable && agentKind !== 'remote' ? 'true' : 'false'}
        data-timestamp-placement={getBubbleTheme(bubbleTheme).timestampPlacement}
        data-action-row-placement={getBubbleTheme(bubbleTheme).actionRowPlacement}
        tabIndex={0}
        onScroll={handleTranscriptScroll}
      >
          {themeUsesIrcGutter(bubbleTheme) ? (
            <span
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize IRC name column"
              className="os-irc-gutter-rail"
              data-testid="irc-gutter-rail"
              data-dragging={ircGutterDragging ? 'true' : 'false'}
              onPointerDown={onIrcRailPointerDown}
              onPointerMove={onIrcRailPointerMove}
              onPointerUp={onIrcRailPointerUp}
              onPointerCancel={onIrcRailPointerUp}
              onDoubleClick={onIrcRailDoubleClick}
            />
          ) : null}
<ChatMessageList {...chatMessageListProps} />
          <ChatBottomDock {...chatBottomDockProps} />
      </div>
    </>
  )
}
