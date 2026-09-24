/**
 * #856 slice 4 — ChatPage's chat-WebSocket lifecycle, moved verbatim.
 *
 * ADR-017 PR-4 / #1131 — the transport is now the whole-SPA multiplex
 * socket (``lib/spaSocket.ts``) instead of a per-conversation WebSocket.
 * Sticky server-side sessions mean an in-flight turn keeps streaming (and
 * the #1113 turn bookends keep flowing to ``agentTurnStore``) after this
 * chat unmounts — that is the root fix for #1118.
 *
 * What this hook still owns: per-chat status, auth-rejection detection,
 * streaming-interrupt-on-close, and reconnect/backoff semantics — mapped
 * onto the mux's socket lifecycle (one socket, many conversations; a close
 * of THE socket is a status change for every mounted chat).
 *
 * All state stays owned by ChatPage and is passed in; ``wsRef`` now holds a
 * mux-backed send adapter with the WebSocket-shaped surface the send paths
 * were written against (``readyState`` + ``send``), so
 * ``useChatSend``/``useChatTurnOps``/tool-decision frames route through the
 * mux without touching their code.
 */
import { useCallback, useEffect, useRef, type Dispatch, type MutableRefObject, type RefObject, type SetStateAction } from 'react'
import {
  reconnectBackoffMs,
  shouldAutoReconnect,
  WS_AUTH_REQUIRED_CODE,
} from '../../lib/chatReconnect'
import type { ChatWsEvent } from '../../lib/chatWs'
import type { ChatConnectionStatus } from '../../lib/chatConnection'
import {
  onSpaStatus,
  sendSpaChat,
  spaLastCloseCode,
  spaStatus,
  subscribeSpa,
  type SpaStatus,
  type SpaSubscription,
} from '../../lib/spaSocket'
import { notifyGenerationComplete } from '../../lib/railOrder'
import { maybeNotifyAgentTurn } from '../../lib/agentNotifications'
import type { ChatMessage } from './chatMessages'

interface NotifyCtx {
  agentId: string | null
  agentName: string
}

interface UseChatWebSocketOptions {
  connectAttempt: number
  conversationId: string
  runtimeBlueprint: string
  teamFromUrl: string
  remoteFromUrl: string
  threadKey: string
  wsRef: MutableRefObject<WebSocket | null>
  handleWsEventRef: RefObject<(event: ChatWsEvent) => void>
  notifyCtxRef: MutableRefObject<NotifyCtx>
  setStatus: Dispatch<SetStateAction<ChatConnectionStatus>>
  setAuthRejected: Dispatch<SetStateAction<boolean>>
  setAwaitingAssistant: Dispatch<SetStateAction<boolean>>
  setThreads: Dispatch<SetStateAction<Record<string, ChatMessage[]>>>
  setConnectAttempt: Dispatch<SetStateAction<number>>
}

export function useChatWebSocket({
  connectAttempt,
  conversationId,
  runtimeBlueprint,
  teamFromUrl,
  remoteFromUrl,
  threadKey,
  wsRef,
  handleWsEventRef,
  notifyCtxRef,
  setStatus,
  setAuthRejected,
  setAwaitingAssistant,
  setThreads,
  setConnectAttempt,
}: UseChatWebSocketOptions): { reconnect: () => void } {
  const backoffAttemptRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const intentionalCloseRef = useRef(false)

  const reconnect = useCallback(() => {
    backoffAttemptRef.current = 0
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    setConnectAttempt((n) => n + 1)
  }, [])

  useEffect(() => {
    intentionalCloseRef.current = false
    setStatus('connecting')
    setAuthRejected(false)

    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }

    const blueprint = teamFromUrl
      ? undefined
      : remoteFromUrl
        ? 'remote_harness'
        : runtimeBlueprint || undefined

    // Mux-backed send adapter: legacy send sites check `readyState` and call
    // `send(frame)`; the frame is wrapped as chat.send for this conversation.
    const sendAdapter = {
      readyState: WebSocket.CLOSED as number,
      send: (frame: string) => sendSpaChat(conversationId, frame),
    }
    wsRef.current = sendAdapter as unknown as WebSocket

    let released = false

    // One mux-status listener drives both this chat's status surface and the
    // adapter's readyState; a socket close runs the interrupt semantics that
    // the per-socket era put in ws.onclose.
    const handleMuxStatus = (muxStatus: SpaStatus) => {
      if (released) return
      sendAdapter.readyState = muxStatus === 'open' ? WebSocket.OPEN : WebSocket.CONNECTING
      setStatus(muxStatus as ChatConnectionStatus)
      if (muxStatus === 'open') {
        backoffAttemptRef.current = 0
        if (spaLastCloseCode() === WS_AUTH_REQUIRED_CODE) setAuthRejected(true)
      } else if (muxStatus === 'closed' || muxStatus === 'failed') {
        setAwaitingAssistant(false)
        const rejected = spaLastCloseCode() === WS_AUTH_REQUIRED_CODE
        setAuthRejected(rejected)
        let interrupted = false
        setThreads((prev) => {
          const current = prev[threadKey]
          if (!current || !current.some((m) => m.streaming)) return prev
          interrupted = true
          return {
            ...prev,
            [threadKey]: current.map((m) => (m.streaming ? { ...m, streaming: false } : m)),
          }
        })
        if (interrupted) {
          const { agentId, agentName } = notifyCtxRef.current
          if (agentId) {
            notifyGenerationComplete(agentId, { failed: true, agentName })
            maybeNotifyAgentTurn({ agentId, agentName, failed: true, selectedAgentId: agentId })
          }
        }
        const attempt = backoffAttemptRef.current
        if (shouldAutoReconnect(spaLastCloseCode() ?? 1006, false, attempt)) {
          const delay = reconnectBackoffMs(attempt)
          backoffAttemptRef.current += 1
          reconnectTimerRef.current = setTimeout(() => {
            reconnectTimerRef.current = null
            setConnectAttempt((n) => n + 1)
          }, delay)
        }
      }
    }

    const statusSub: SpaSubscription = onSpaStatus(handleMuxStatus)
    const sub = subscribeSpa(
      conversationId,
      (event) => {
        if (released) return
        handleWsEventRef.current?.(event)
      },
      blueprint,
    )

    // subscribeSpa ensured the socket exists; reflect whatever state the mux
    // is already in (a previously-mounted chat may have opened it already,
    // in which case no status transition will fire).
    handleMuxStatus(spaStatus())

    return () => {
      released = true
      statusSub.release()
      sub.release()
      // Sticky: releasing the subscription does NOT unsubscribe the server
      // session (#1118). The mux singleton outlives this chat.
      if (wsRef.current === (sendAdapter as unknown as WebSocket)) wsRef.current = null
      intentionalCloseRef.current = true
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectAttempt, conversationId, runtimeBlueprint, teamFromUrl])

  return { reconnect }
}
