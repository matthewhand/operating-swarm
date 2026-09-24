/**
 * #856 slice 16 — CLI session ops, turn interrupt, suggestion chips and
 * message-edit save, verbatim from ChatPage.
 *
 * startFreshCliSession / retryCliSession / clearCliSessionHistory (#499
 * recovery surface), interruptRunningTurn (#198 enter-to-interrupt), the
 * SUGGESTION_CHIP_EVENT listener, and saveEditedMessage (optimistic edit +
 * WS edit frame + PATCH, with the #6xx cli_session_reset toast). Threads,
 * ws and refs stay page-owned.
 */
import { useCallback, useEffect } from 'react'
import { agentIdFromBlueprint, clearAgentThread, patchAgentMessage, setConversationIdForAgent, DEFAULT_AGENT_ID } from '../../lib/agentChat'
import { buildCancelTurnFrame, buildChatWsEditFrame, newConversationId } from '../../lib/chatWs'
import { SUGGESTION_CHIP_EVENT, suggestionChipText } from '../../lib/chatQueue'
import { turnIndexFromDisplay } from '../../lib/transcriptReconstruct'
import type { ChatMessage } from './chatMessages'

export interface UseChatTurnOpsOptions {
  selectedBlueprint: string | null
  setSearchParams: (updater: (prev: URLSearchParams) => URLSearchParams) => void
  messages: ChatMessage[]
  submitUserText: (text: string) => void
  conversationId: string
  threadKey: string
  threads: Record<string, ChatMessage[]>
  setThreads: (updater: (prev: Record<string, ChatMessage[]>) => Record<string, ChatMessage[]>) => void
  wsRef: { current: WebSocket | null }
  lastUserTextRef: { current: string }
  conversationIdRef: { current: string }
  messagesEditable: boolean
  setAwaitingAssistant: (value: boolean) => void
  setEditingKey: (key: string | null) => void
  addToast: (toast: { type: 'info' | 'error' | 'success'; title: string; message: string }) => void
}

export function useChatTurnOps(opts: UseChatTurnOpsOptions) {
  const {
    selectedBlueprint,
    setSearchParams,
    messages,
    submitUserText,
    conversationId,
    threadKey,
    threads,
    setThreads,
    wsRef,
    lastUserTextRef,
    conversationIdRef,
    messagesEditable,
    setAwaitingAssistant,
    setEditingKey,
    addToast,
  } = opts

  const startFreshCliSession = useCallback(() => {
    const agent = agentIdFromBlueprint(selectedBlueprint)
    const minted = newConversationId()
    setConversationIdForAgent(agent, minted)
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (agent && agent !== DEFAULT_AGENT_ID) next.set('blueprint', agent)
      next.set('session', minted)
      return next
    })
  }, [selectedBlueprint, setSearchParams])

  const retryCliSession = useCallback(() => {
    const lastUser = [...messages].reverse().find((row) => row.role === 'user')
    const text = (lastUserTextRef.current || lastUser?.text || '').trim()
    if (text) submitUserText(text)
  }, [messages, submitUserText])

  const clearCliSessionHistory = useCallback(() => {
    const agent = agentIdFromBlueprint(selectedBlueprint)
    const previousId = conversationId
    setThreads((prev) => ({ ...prev, [threadKey]: [] }))
    void clearAgentThread(agent, previousId).catch(() => undefined)
    startFreshCliSession()
  }, [conversationId, selectedBlueprint, startFreshCliSession, threadKey])

  /**
   * #198: interrupt the turn in flight (enter-to-interrupt on a queued send).
   * The drain effect promotes the top queued row automatically once the
   * cancelled turn closes, so this only needs to request the cancel.
   *
   * #1096: an optional `agent` scopes the cancel — the stop button on the
   * generating agent's transcript row interrupts THAT agent's turn only;
   * other concurrent turns keep streaming (#1097 seam). Bare calls keep the
   * legacy behavior (cancel the active turn).
   *
   * ADR-017 PR-2: an optional `turnId` (from the server's `turn_started`
   * bookend, tracked in the SPA turn registry) names the exact turn, so a
   * stop cannot misfire onto a newer turn of the same agent that began
   * after the button rendered.
   */
  const interruptRunningTurn = useCallback((agent?: string, turnId?: string) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(buildCancelTurnFrame(agent, turnId))
      setAwaitingAssistant(false)
    }
  }, [])

  useEffect(() => {
    const onChip = (event: Event) => {
      const text = suggestionChipText(event)
      if (text.trim()) submitUserText(text)
    }
    window.addEventListener(SUGGESTION_CHIP_EVENT, onChip)
    return () => {
      window.removeEventListener(SUGGESTION_CHIP_EVENT, onChip)
    }
  }, [submitUserText])

  const saveEditedMessage = useCallback(
    async (index: number, nextText: string) => {
      if (!messagesEditable) return
      const current = threads[threadKey] ?? []
      const target = current[index]
      if (!target || target.streaming) return
      setThreads((prev) => {
        const list = prev[threadKey] ?? []
        if (!list[index]) return prev
        const next = list.slice()
        next[index] = { ...next[index], text: nextText, edited: true }
        return { ...prev, [threadKey]: next }
      })
      setEditingKey(null)
      const turnIndex = turnIndexFromDisplay(current, index)
      const ws = wsRef.current
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(buildChatWsEditFrame(turnIndex, nextText))
      }
      try {
        const patched = await patchAgentMessage(
          agentIdFromBlueprint(selectedBlueprint),
          {
            index: turnIndex,
            content: nextText,
            conversation_id: conversationIdRef.current,
          },
        )
        if (patched.cli_session_reset) {
          addToast({
            type: 'info',
            title: 'CLI session restarted',
            message:
              'A message was edited and the CLI session cannot rewind. The next message starts a fresh session.',
          })
        }
      } catch {
        addToast({
          type: 'error',
          title: 'Could not save edit',
          message: 'The message was updated in this view, but persist failed.',
        })
      }
    },
    [addToast, messagesEditable, selectedBlueprint, threadKey, threads],
  )


  return { startFreshCliSession, retryCliSession, clearCliSessionHistory, interruptRunningTurn, saveEditedMessage }
}
