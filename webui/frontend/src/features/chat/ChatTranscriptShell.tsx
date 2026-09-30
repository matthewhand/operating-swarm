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
    HostCliTip,
    RoleAgentTip,
    VanillaSetupTip,
    activeChatAgentId,
    agentKind,
    bubbleTheme,
    composerInsetCustomProperty,
    composerInsetPx,
    dismissDefaultLlmTip,
    dismissHostCliTip,
    dismissRoleTip,
    getBubbleTheme,
    handleTranscriptScroll,
    hostCliTipName,
    ircGutterDragging,
    ircGutterPx,
    isCliAgent,
    isRemoteAgent,
    messagesEditable,
    neverShowHostCliTip,
    onIrcRailDoubleClick,
    onIrcRailPointerDown,
    onIrcRailPointerMove,
    onIrcRailPointerUp,
    remoteFromUrl,
    scrollBoxRef,
    showDefaultLlmTip,
    showHostCliTip,
    showRoleTip,
    statusLabel,
    themeUsesIrcGutter,
} = props

  return (
    <>
      <ConsumerPills providerId={activeChatAgentId} />
      {/* ONE first-run tip slot, topmost so it reads as a startup hint, above
          the seat-contextual role tip. Two owners can want it — `HostCliTip`
          (#1703: a CLI on PATH that is not wired up yet) and
          `VanillaSetupTip` (#1700 (3): no inference configured at all) — so the
          slot renders AT MOST ONE, via if/else rather than two conditionals.
          Exclusivity is decided upstream in `firstVanillaTip`, which stands
          down while a detected CLI owns the cheaper keyless fix; the `else` is
          the belt on that pair, so a future owner cannot silently stack a
          second explanation of the same "you cannot talk to anything yet". */}
      {showHostCliTip && hostCliTipName ? (
        <HostCliTip
          cliName={hostCliTipName}
          onDismiss={dismissHostCliTip}
          onNeverShowAgain={neverShowHostCliTip}
        />
      ) : (
        VanillaSetupTip || null
      )}
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
<ChatMessageList {...props} />
          <ChatBottomDock {...props} />
      </div>
    </>
  )
}
