/**
 * #856 slice 4 — ChatPage's chat-WebSocket lifecycle, moved verbatim.
 *
 * Owns connect/reconnect/backoff, auth-rejection detection, streaming-turn
 * interrupt handling on close, and the #738 mid-handshake teardown dance.
 * All state stays owned by ChatPage and is passed in; the moved effect body
 * is verbatim, including its dependency array (remoteFromUrl / threadKey are
 * read via closure exactly as before — the deps list is unchanged).
 */
import { useCallback, useEffect, useRef, type Dispatch, type MutableRefObject, type RefObject, type SetStateAction } from 'react'
import {
  reconnectBackoffMs,
  shouldAutoReconnect,
  WS_AUTH_REQUIRED_CODE,
} from '../../lib/chatReconnect'
import { buildChatWsUrl, parseChatWsMessage, type ChatWsEvent } from '../../lib/chatWs'
import type { ChatConnectionStatus } from '../../lib/chatConnection'
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
  /** Consecutive auto-reconnect attempts since last successful open. */
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
    let opened = false
    intentionalCloseRef.current = false
    setStatus('connecting')
    setAuthRejected(false)

    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }

    let ws: WebSocket
    try {
      ws = new WebSocket(
        buildChatWsUrl(
          conversationId,
          teamFromUrl ? undefined : remoteFromUrl ? 'remote_harness' : runtimeBlueprint || undefined,
        ),
      )
    } catch {
      setStatus('failed')
      const attempt = backoffAttemptRef.current
      if (shouldAutoReconnect(1006, false, attempt)) {
        const delay = reconnectBackoffMs(attempt)
        backoffAttemptRef.current = attempt + 1
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null
          setConnectAttempt((n) => n + 1)
        }, delay)
      }
      return () => {
        if (reconnectTimerRef.current) {
          clearTimeout(reconnectTimerRef.current)
          reconnectTimerRef.current = null
        }
      }
    }
    wsRef.current = ws

    ws.onopen = () => {
      opened = true
      backoffAttemptRef.current = 0
      setStatus('open')
    }
    ws.onmessage = (event: MessageEvent) => {
      if (typeof event.data === 'string') {
        handleWsEventRef.current?.(parseChatWsMessage(event.data))
      }
    }
    ws.onclose = (event: CloseEvent) => {
      if (wsRef.current === ws) wsRef.current = null
      setAwaitingAssistant(false)
      const rejected = event.code === WS_AUTH_REQUIRED_CODE
      setAuthRejected(rejected)
      setStatus(opened ? 'closed' : 'failed')
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
          notifyGenerationComplete(agentId, {
            failed: true,
            agentName,
          })
          maybeNotifyAgentTurn({
            agentId,
            agentName,
            failed: true,
            selectedAgentId: agentId,
          })
        }
      }

      const attempt = backoffAttemptRef.current
      if (shouldAutoReconnect(event.code, intentionalCloseRef.current, attempt)) {
        const delay = reconnectBackoffMs(attempt)
        backoffAttemptRef.current = attempt + 1
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null
          setConnectAttempt((n) => n + 1)
        }, delay)
      }
    }

    return () => {
      intentionalCloseRef.current = true
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      ws.onopen = null
      ws.onmessage = null
      if (ws.readyState === 0) {
        // #738: closing during CONNECTING is what Chrome logs as "WebSocket
        // is closed before the connection established". Defer to the next
        // macrotask: if the handshake completes first, close() is legal from
        // OPEN (silent); if it fails first, onclose already ran and the
        // guard below makes close() a no-op. Either way no mid-handshake
        // teardown, and handlers are already detached so no events leak.
        setTimeout(() => {
          try {
            ws.close()
          } catch {
            /* already closed */
          }
          if (wsRef.current === ws) wsRef.current = null
        }, 0)
      } else {
        ws.onclose = null
        ws.close()
        if (wsRef.current === ws) wsRef.current = null
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectAttempt, conversationId, runtimeBlueprint, teamFromUrl])

  return { reconnect }
}
