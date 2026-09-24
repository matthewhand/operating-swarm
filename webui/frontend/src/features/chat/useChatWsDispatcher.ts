/**
 * #856 slice 5 — ChatPage's WS frame dispatcher, moved verbatim.
 *
 * Owns the per-frame routing: unknown-frame warning, spa hello, context
 * usage, aux task frames, tool status/question attachments, suggestion
 * chips, PR/teammate/subagent transcript frames, generation-complete
 * notifications, and #96 unread marking. All state stays owned by
 * ChatPage; callbacks and setters are passed in. Deps array is unchanged.
 */
import { useCallback, type Dispatch, type MutableRefObject, type SetStateAction } from 'react'
import {
  applyAuxFrame,
  announceAuxTasks,
  type AuxTask,
} from '../../lib/auxTasks'
import {
  publishContextUsage,
  type ContextUsage,
} from '../../lib/contextUsage'
import { publishExpectedSpaVersion } from '../../lib/spaHello'
import { markAgentUnread } from '../../lib/unreadAgents'
import {
  summarizeUnknownWsFrame,
  type ChatWsEvent,
} from '../../lib/chatWs'
import { applyTurnFrame, recordTurnFrame, type TurnSnapshot } from '../../lib/agentTurns'
import type { DecisionQuestion } from '../../lib/decisionQuestion'
import { parseDecisionQuestion, stripDecisionQuestion } from '../../lib/decisionQuestion'
import { registerDynamicSubagent } from '../../lib/dynamicSubagents'
import { isToolAlwaysAllowed, type ToolCallState } from '../../lib/safety'
import { isCompressionNoticeText } from '../../lib/compressionNotices'
import { isSwarmOwnedAgent } from '../../lib/agentKind'
import { CLI_TERMINATED_STATUS } from '../../lib/cliRunState'
import { insertCliSessionNotice } from '../../lib/chatTranscript'
import { notifyGenerationComplete } from '../../lib/railOrder'
import { maybeNotifyAgentTurn } from '../../lib/agentNotifications'
import type { ChatMessage } from './chatMessages'

interface UseChatWsDispatcherOptions {
  activeChatAgentId: string | null
  attachQuestionToThread: (question: DecisionQuestion, blocking: boolean) => void
  attachToolToThread: (tool: ToolCallState) => void
  sendToolDecision: (id: string, decision: 'allow' | 'always' | 'deny') => void
  threadKey: string
  useSuggestions: boolean
  seatUnread: boolean
  pinnedToBottomRef: MutableRefObject<boolean>
  setContextUsage: Dispatch<SetStateAction<ContextUsage | null>>
  setAgentTurns: Dispatch<SetStateAction<TurnSnapshot>>
  setAuxTasks: Dispatch<SetStateAction<AuxTask[]>>
  setSuggestionChips: Dispatch<SetStateAction<string[]>>
  setThreads: Dispatch<SetStateAction<Record<string, ChatMessage[]>>>
  setUnreadIds: Dispatch<SetStateAction<string[]>>
  selectedBlueprint: string
  userKeyCounterRef: MutableRefObject<number>
  notifyCtxRef: MutableRefObject<{
    agentId: string | null
    agentName: string
    agentKind: string
    blueprintId: string
  }>
}

export function useChatWsDispatcher(options: UseChatWsDispatcherOptions) {
  const {
    activeChatAgentId,
    attachQuestionToThread,
    attachToolToThread,
    sendToolDecision,
    threadKey,
    useSuggestions,
    seatUnread,
    pinnedToBottomRef,
    setContextUsage,
    setAgentTurns,
    setAuxTasks,
    setSuggestionChips,
    setThreads,
    setUnreadIds,
    selectedBlueprint,
    userKeyCounterRef,
    notifyCtxRef,
  } = options
  const handleWsEvent = useCallback(
    (event: ChatWsEvent) => {
      if (event.kind === 'unknown') {
        console.warn('Unrecognised chat websocket frame:', summarizeUnknownWsFrame(event.raw))
        return
      }
      if (event.kind === 'spa_hello') {
        publishExpectedSpaVersion(event.spaVersion)
        return
      }
      if (event.kind === 'turn_started' || event.kind === 'turn_finished') {
        // ADR-017 PR-2: fold the bookend into the SPA turn registry so the
        // row stop can name the exact turn_id when it cancels (#1113).
        recordTurnFrame(event)
        setAgentTurns((prev) => applyTurnFrame(prev, event))
        return
      }
      if (event.kind === 'context_usage') {
        publishContextUsage(event.usage)
        setContextUsage(event.usage)
        return
      }
      if (event.kind === 'aux_started' || event.kind === 'aux_update') {
        // #818: background LLM work surfaces in the navbar indicator.
        setAuxTasks((prev) => {
          const next = applyAuxFrame(
            prev,
            event.kind === 'aux_started'
              ? { type: 'aux_task_started', ...event.task }
              : { type: 'aux_task_update', ...event.task },
          )
          announceAuxTasks(next)
          return next
        })
        return
      }
      if (event.kind === 'tool_status') {
        attachToolToThread({
          id: event.id,
          name: event.name,
          status: event.status,
          agentId: event.agentId,
          needsApproval: false,
        })
        return
      }
      if (event.kind === 'user_question') {
        attachQuestionToThread(event.question, true)
        return
      }
      if (event.kind === 'suggestions') {
        if (!useSuggestions) {
          setSuggestionChips([])
          return
        }
        setSuggestionChips(event.suggestions)
        return
      }
      if (event.kind === 'pr_opened') {
        setThreads((prev) => {
          const current = prev[threadKey] ?? []
          return {
            ...prev,
            [threadKey]: [
              ...current,
              {
                key: `pr-opened-${current.length}-${Date.now()}`,
                role: 'status' as const,
                text: '',
                streaming: false,
                ts: new Date().toISOString(),
                prOpened: event.event,
              },
            ],
          }
        })
        return
      }
      if (event.kind === 'teammate_task') {
        setThreads((prev) => {
          const current = prev[threadKey] ?? []
          return {
            ...prev,
            [threadKey]: [
              ...current,
              {
                key: `teammate-task-${current.length}-${Date.now()}`,
                role: 'status' as const,
                text: '',
                streaming: false,
                ts: new Date().toISOString(),
                teammateTask: event.event,
              },
            ],
          }
        })
        return
      }
      if (event.kind === 'subagent_fan_out') {
        setThreads((prev) => {
          const current = prev[threadKey] ?? []
          return {
            ...prev,
            [threadKey]: [
              ...current,
              {
                key: `subagent-fan-out-${current.length}-${Date.now()}`,
                role: 'assistant' as const,
                text: '',
                streaming: false,
                ts: new Date().toISOString(),
                subagentFanOut: event.event,
              },
            ],
          }
        })
        for (const s of event.event.subagents ?? []) {
          registerDynamicSubagent({
            id: s.id,
            name: s.name,
            parentAgentId: s.parentAgentId,
            role: s.role,
            status: s.status,
            summary: s.summary,
            task: s.task,
          })
        }
        return
      }
      if (event.kind === 'tool_approval') {
        const agentId = event.agentId || selectedBlueprint || threadKey
        if (isToolAlwaysAllowed(agentId, event.name)) {
          sendToolDecision(event.id, 'always')
          attachToolToThread({
            id: event.id,
            name: event.name,
            status: 'allowed',
            agentId,
            needsApproval: false,
            concerned: true,
          })
          return
        }
        attachToolToThread({
          id: event.id,
          name: event.name,
          status: 'running',
          agentId,
          needsApproval: true,
          concerned: true,
        })
        return
      }
      setThreads((prev) => {
        const current = prev[threadKey] ?? []
        let next = current
        switch (event.kind) {
          case 'user_echo':
            userKeyCounterRef.current += 1
            next = [
              ...current,
              {
                key: `user-${userKeyCounterRef.current}-${Date.now()}`,
                role: 'user',
                text: event.text,
                streaming: false,
                ts: new Date().toISOString(),
              },
            ]
            break
          case 'assistant_start':
            if (current.some((m) => m.key === event.id)) return prev
            next = [
              ...current,
              // #774: stamp arrival time now — the row's clock must not wait
              // for final text, or the IRC gutter shows nothing for the turn.
              { key: event.id, role: 'assistant', text: '', streaming: true, ts: new Date().toISOString() },
            ]
            break
          case 'assistant_chunk':
            next = current.map((m) =>
              m.key === event.id ? { ...m, text: m.text + event.text } : m,
            )
            break
          case 'assistant_final':
            next = current.map((m) => {
              if (m.key !== event.id) return m
              const fence = parseDecisionQuestion(event.text)
              const rawResp =
                typeof (event as { raw_response?: string }).raw_response === 'string'
                  ? (event as { raw_response?: string }).raw_response
                  : m.rawResponse
              return {
                ...m,
                text: fence ? stripDecisionQuestion(event.text) : event.text,
                rawResponse: rawResp,
                streaming: false,
                question: m.question ?? fence ?? undefined,
                questionBlocking: m.questionBlocking ?? false,
              }
            })
            break
          case 'status':
            // #534: compression notices belong to API seats only. Remote/CLI
            // seats manage their own context — never show the notice.
            if (
              isCompressionNoticeText(event.text) &&
              !isSwarmOwnedAgent(notifyCtxRef.current.blueprintId, notifyCtxRef.current.agentKind)
            ) {
              break
            }
            if (
              event.text === CLI_TERMINATED_STATUS &&
              current.some((row) => row.role === 'status' && row.text === CLI_TERMINATED_STATUS)
            ) {
              next = current.map((row) => (row.streaming ? { ...row, streaming: false } : row))
              break
            }
            next = insertCliSessionNotice(current, {
              key: `status-${current.length}-${Date.now()}`,
              role: 'status',
              text: event.text,
              streaming: false,
              ts: new Date().toISOString(),
              rateLimit: event.rateLimit,
            })
            break
        }
        return { ...prev, [threadKey]: next }
      })
      if (event.kind === 'assistant_final') {
        const { agentId, agentName } = notifyCtxRef.current
        if (agentId) {
          notifyGenerationComplete(agentId, {
            snippet: event.text,
            agentName,
          })
          maybeNotifyAgentTurn({
            agentId,
            agentName,
            snippet: event.text,
            selectedAgentId: agentId,
          })
        }
        // #96: a turn finishing on the open-but-scrolled-up seat was never
        // seen — mark it unread (the rail only dots unselected seats today).
        if (
          agentId &&
          !seatUnread &&
          !pinnedToBottomRef.current &&
          !(typeof document !== 'undefined' && document.visibilityState === 'hidden')
        ) {
          setUnreadIds(markAgentUnread(agentId))
        }
      }
    },
    [
      activeChatAgentId,
      attachQuestionToThread,
      attachToolToThread,
      sendToolDecision,
      threadKey,
      useSuggestions,
      seatUnread,
    ],
  )
  return handleWsEvent
}
