/**
 * #856 slice 15 — compact/summary turn commands, verbatim from ChatPage.
 *
 * handleCompact (#636 CLI-compact-via-summary + fresh session; API thread
 * summary + usage publish), handleCompressToHere (#637 span compaction),
 * applyStartFromHere (#639 context-cull confirm flow), and the two menu
 * dispatchers that close the composer menus first. All state (summaries,
 * usage, warning, strategy) stays page-owned.
 */
import { useCallback } from 'react'
import type { ChatMessage } from './chatMessages'
import { agentIdFromBlueprint, compactAgentThread, startContextFromHere } from '../../lib/agentChat'
import { START_CONTEXT_FROM_HERE_LABEL, overFullWarningCopy, type ContextMeta } from '../../lib/contextCull'
import { rawOffsetForMessage } from '../../lib/chatCompact'
import { compactCliThread } from '../../lib/cliCompact'
import { dispatchCliSessionHopped } from '../../lib/cliSessionHop'
import { publishContextUsage } from '../../lib/contextUsage'
import type { ConversationSummary } from '../../lib/chatCompact'
import type { ContextUsage } from '../../lib/contextUsage'

export interface UseChatCompactOptions {
  messages: ChatMessage[]
  conversationId: string
  selectedBlueprint: string | null
  teamFromUrl: string | null
  threadKey: string
  isCliAgent: boolean
  currentCli: string
  selectedCli: { cli: string } | null | undefined
  llmDefaultReady: boolean
  cliCompactCapableMap: Record<string, unknown> | undefined
  cullTriggerPct: number
  contextStrategy: string
  contextMaxRef: { current: number | null }
  setSummariesByThread: (updater: (prev: Record<string, ConversationSummary[]>) => Record<string, ConversationSummary[]>) => void
  setContextMeta: (meta: ContextMeta) => void
  setContextUsage: (usage: ContextUsage | null) => void
  setStartFromHereWarning: (value: { message: ChatMessage; startOffset: number; copy: string } | null) => void
  setPlusOpen: (open: boolean) => void
  setContextMenu: (value: null) => void
  setConversationId: (id: string) => void
  addToast: (toast: { type: 'info' | 'error' | 'success'; title: string; message: string }) => void
}

export function useChatCompact(opts: UseChatCompactOptions) {
  const {
    messages,
    conversationId,
    selectedBlueprint,
    teamFromUrl,
    threadKey,
    isCliAgent,
    currentCli,
    selectedCli,
    llmDefaultReady,
    cliCompactCapableMap,
    cullTriggerPct,
    contextStrategy,
    contextMaxRef,
    setSummariesByThread,
    setContextMeta,
    setContextUsage,
    setStartFromHereWarning,
    setPlusOpen,
    setContextMenu,
    setConversationId,
    addToast,
  } = opts
  const cliCompactMap = cliCompactCapableMap

  const handleCompact = useCallback(async () => {
    setPlusOpen(false)
    if (messages.length === 0) {
      addToast({
        type: 'info',
        title: 'Compact',
        message: 'Nothing to compact yet.',
      })
      return
    }
    // #636: a CLI seat compacts through the same server-side summary and then
    // starts a fresh CLI session carrying it. The old provider transcript
    // stays on disk; the new process starts clean with the summary in context.
    if (isCliAgent) {
      const cliName = currentCli || selectedCli?.cli || ''
      if (!cliName) {
        addToast({
          type: 'error',
          title: 'Compact failed',
          message: 'No CLI is resolved for this seat.',
        })
        return
      }
      try {
        const result = await compactCliThread({
          conversationId,
          agentId: selectedBlueprint || '',
          cli: cliName,
          messages: messages
            .filter((message) => message.role === 'user' || message.role === 'assistant')
            .map((message) => ({ role: message.role, content: message.text })),
          defaultLlmReady: llmDefaultReady,
          cliCompactCapable: Boolean(cliCompactMap?.[cliName]),
        })
        dispatchCliSessionHopped({
          agentId: selectedBlueprint || '',
          conversationId: result.newConversationId,
          status: result.status,
          fromCli: cliName,
          toCli: cliName,
        })
        setConversationId(result.newConversationId)
      } catch (err) {
        const detail = err instanceof Error ? err.message.trim() : ''
        addToast({
          type: 'error',
          title: 'Compact failed',
          message: detail || 'Could not compact this chat. Sign in and try again.',
        })
      }
      return
    }
    try {
      const result = await compactAgentThread({
        conversationId,
        agentId: teamFromUrl || agentIdFromBlueprint(selectedBlueprint),
        messages: messages
          .filter((message) => message.role === 'user' || message.role === 'assistant')
          .map((message) => ({
            role: message.role,
            content: message.text,
          })),
      })
      setSummariesByThread((prev) => ({ ...prev, [threadKey]: result.summaries }))
      if (result.usage) {
        publishContextUsage(result.usage)
        setContextUsage(result.usage)
      }
    } catch (err) {
      const detail = err instanceof Error ? err.message.trim() : ''
      addToast({
        type: 'error',
        title: 'Compact failed',
        message: detail || 'Could not compact this chat. Sign in and try again.',
      })
    }
  }, [addToast, conversationId, messages, selectedBlueprint, teamFromUrl, threadKey, isCliAgent, currentCli, selectedCli, llmDefaultReady, cliCompactMap])

  const handleCompressToHere = useCallback(
    async (message: ChatMessage) => {
      setPlusOpen(false)
      setContextMenu(null)
      const rawMessages = messages.filter(
        (row) => row.role === 'user' || row.role === 'assistant',
      )
      const spanEnd = rawOffsetForMessage(messages, message.key)
      if (spanEnd < 0 || rawMessages.length === 0) {
        addToast({
          type: 'info',
          title: 'Compress',
          message: 'Nothing to compact yet.',
        })
        return
      }
      try {
        const result = await compactAgentThread({
          conversationId,
          agentId: teamFromUrl || agentIdFromBlueprint(selectedBlueprint),
          messages: rawMessages.map((row) => ({
            role: row.role,
            content: row.text,
          })),
          spanStart: 0,
          spanEnd,
        })
        setSummariesByThread((prev) => ({ ...prev, [threadKey]: result.summaries }))
        if (result.usage) {
          publishContextUsage(result.usage)
          setContextUsage(result.usage)
        }
      } catch (err) {
        const detail = err instanceof Error ? err.message.trim() : ''
        addToast({
          type: 'error',
          title: 'Compact failed',
          message: detail || 'Could not compact this chat. Sign in and try again.',
        })
      }
    },
    [addToast, conversationId, messages, selectedBlueprint, teamFromUrl, threadKey],
  )

  const applyStartFromHere = useCallback(
    async (message: ChatMessage, confirm: boolean) => {
      const rawMessages = messages.filter(
        (row) => row.role === 'user' || row.role === 'assistant',
      )
      const startOffset = rawOffsetForMessage(messages, message.key)
      if (startOffset < 0 || rawMessages.length === 0) {
        addToast({
          type: 'info',
          title: START_CONTEXT_FROM_HERE_LABEL,
          message: 'Nothing to start from yet.',
        })
        return
      }
      try {
        const result = await startContextFromHere({
          conversationId,
          agentId: teamFromUrl || agentIdFromBlueprint(selectedBlueprint),
          messages: rawMessages.map((row) => ({
            role: row.role,
            content: row.text,
          })),
          startOffset,
          confirm,
          contextMax: contextMaxRef.current,
        })
        if (result.warning && !result.applied) {
          const pct = typeof result.estimated_pct === 'number' ? result.estimated_pct : 0
          const trigger = result.cull_trigger_pct ?? cullTriggerPct
          setStartFromHereWarning({
            message,
            startOffset,
            copy: result.info || overFullWarningCopy(pct, trigger),
          })
          return
        }
        if (result.context_meta) setContextMeta(result.context_meta)
        setStartFromHereWarning(null)
      } catch {
        addToast({
          type: 'error',
          title: START_CONTEXT_FROM_HERE_LABEL,
          message: 'Could not start context from here. Sign in and try again.',
        })
      }
    },
    [addToast, conversationId, cullTriggerPct, messages, selectedBlueprint, teamFromUrl],
  )

  const handleStartContextFromHere = useCallback(
    (message: ChatMessage) => {
      setPlusOpen(false)
      setContextMenu(null)
      void applyStartFromHere(message, false)
    },
    [applyStartFromHere],
  )

  const handleContextToHere = useCallback(
    (message: ChatMessage) => {
      if (contextStrategy === 'cull') {
        handleStartContextFromHere(message)
        return
      }
      void handleCompressToHere(message)
    },
    [contextStrategy, handleCompressToHere, handleStartContextFromHere],
  )


  return { handleCompact, handleCompressToHere, applyStartFromHere, handleStartContextFromHere, handleContextToHere }
}
