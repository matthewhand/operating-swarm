/**
 * #636 — orchestrating a CLI-seat compact: summarise server-side (the same
 * POST /chat/compact/ the API flow uses), then start a fresh CLI session via
 * the existing start_new select path so the new process carries the summary.
 */
import { apiPost } from './api'
import {
  agentIdFromBlueprint,
  setConversationIdForAgent,
} from './agentChat'
import { dispatchCliSessionSwitched } from './cliSessions'
import type { CompactResult } from './agentChat'

/** The orchestrator's result: what ChatPage needs to repaint the seat. */
export interface CompactCliResult {
  summaryBody: string
  newConversationId: string
  status: string
}

export async function compactCliThread(opts: {
  conversationId: string
  agentId: string
  cli: string
  messages: Array<{ role: string; content: string }>
  defaultLlmReady?: boolean
  cliCompactCapable?: boolean
}): Promise<CompactCliResult> {
  if (!opts.defaultLlmReady && !opts.cliCompactCapable) {
    throw new Error(
      'No API is configured — compacting a CLI seat needs a default API profile',
    )
  }
  if (opts.messages.length === 0) {
    throw new Error('Nothing to compact yet.')
  }

  const agent = agentIdFromBlueprint(opts.agentId)
  // (a) The summary, exactly as the API flow produces it — it lands in the
  // summaries strip and stays context-togglable.
  const compact = await apiPost<CompactResult>('/chat/compact/', {
    conversation_id: opts.conversationId,
    agent,
    messages: opts.messages.filter(
      (row) => row.role === 'user' || row.role === 'assistant',
    ),
  })
  const summaries = compact?.summaries ?? []
  const summary = compact?.summary ?? summaries[summaries.length - 1]
  if (!summary) {
    throw new Error('Compact returned no summary')
  }

  // (b) A fresh CLI session for the same seat via the existing start_new
  // select path — the new process starts clean with the summary carried, the
  // old provider transcript stays on disk.
  const select = await apiPost<{
    conversation_id?: string
    status?: string
  }>('/v1/cli-sessions/select/', {
    agent,
    cli: opts.cli,
    start_new: true,
    from_conversation_id: opts.conversationId,
  })
  const newConversationId = (select.conversation_id || '').trim()
  if (!newConversationId) {
    throw new Error('Could not start a new CLI session after compact')
  }
  setConversationIdForAgent(opts.agentId, newConversationId)
  const status = (select.status || '').trim()
  dispatchCliSessionSwitched({
    agentId: opts.agentId,
    conversationId: newConversationId,
    status: status || 'Started a new CLI session.',
  })

  return {
    summaryBody: summary.body,
    newConversationId,
    status: status || 'Started a new CLI session.',
  }
}
