/**
 * #856 slice 1 — ChatPage module-scope message/session surface, moved verbatim.
 *
 * Owns the wire/transcript shape (ChatMessage), thread-row hydration, and the
 * Django session-gate login helpers. ChatPage re-imports these and re-exports
 * the login helpers, so both the component body and the pages/ChatPage import
 * surface are unchanged.
 */
import { isCompressionNoticeText } from '../../lib/compressionNotices'
import { asTranscriptRole } from '../../lib/chatStatus'
import {
  isRateLimitWait,
  type RateLimitWait,
} from '../../lib/providerRateLimits'
import { parsePrOpened } from '../../lib/prOpened'
import { parseTeammateTask } from '../../lib/teammateTask'
import { parseSubagentFanOut } from '../../lib/subagentFanOut'
import type { PrOpenedEvent } from '../../lib/prOpened'
import type { TeammateTaskEvent } from '../../lib/teammateTask'
import type { SubagentFanOutData } from '../../lib/subagentFanOut'
import type { ToolCallState } from '../../lib/safety'
import type { DecisionQuestion } from '../../lib/decisionQuestion'

export interface ChatMessage {
  /** Stable key; for assistant messages this is the server-issued container id. */
  key: string
  role: 'user' | 'assistant' | 'status' | 'system'
  text: string
  /** True while the assistant message is still streaming. */
  streaming: boolean
  /** #1149: user row echoed optimistically, not yet confirmed by the server. */
  pending?: boolean
  /** #1168: optimistic row the server never confirmed — resend offered. */
  sendFailed?: boolean
  tools?: ToolCallState[]
  /** Blocking ``ask_user`` card or a non-blocking ```question fence. */
  question?: DecisionQuestion
  questionBlocking?: boolean
  questionAnswered?: boolean
  edited?: boolean
  /** REQ-71 chrome — structured PR-opened tool result, not markdown. */
  prOpened?: PrOpenedEvent
  /** REQ-84 chrome — team task whose worker is a configured remote. */
  teammateTask?: TeammateTaskEvent
  subagentFanOut?: SubagentFanOutData
  /** REQ-104 — expandable archive of the previous swarm thread. */
  kind?: 'prior_history'
  /** #527 — openai-agents persona that produced the row, when the server says. */
  persona?: string
  /** Persist/reload timestamp (ISO). Status/info chrome shows this. */
  ts?: string
  /** REQ-88 — provider queue wait; click opens that provider's rate-limit fields. */
  rateLimit?: RateLimitWait
  /** Terminal CLI/config failure — recovery banner (#274). */
  fatalConfigError?: boolean
  /** #850: Raw unstripped terminal response captured from Herdr. */
  rawResponse?: string
}

/** #534: persisted compression rows never render on restored transcripts. */
export function hydrateThreadRows(messages: Array<Parameters<typeof chatMessageFromThreadRow>[0]>): ChatMessage[] {
  return messages
    .filter((message) => !(message.role === 'status' && isCompressionNoticeText(message.content)))
    .map(chatMessageFromThreadRow)
}

export function chatMessageFromThreadRow(
  message: {
    role: string
    content: string
    edited?: boolean
    kind?: string
    ts?: string
    rate_limit?: RateLimitWait
    fatal_config_error?: boolean
    persona?: string
    raw_response?: string
  },
  index: number,
): ChatMessage {
  const prOpened = parsePrOpened(message.content) ?? undefined
  const teammateTask = parseTeammateTask(message.content) ?? undefined
  const subagentFanOut = parseSubagentFanOut(message.content) ?? undefined
  const prior = message.kind === 'prior_history'
  return {
    key: `hist-${index}-${message.role}`,
    role: prior ? 'system' : asTranscriptRole(message.role),
    text: prOpened || teammateTask || subagentFanOut ? '' : message.content,
    rawResponse: typeof message.raw_response === 'string' ? message.raw_response : undefined,
    streaming: false,
    edited: message.edited === true,
    prOpened,
    teammateTask,
    subagentFanOut,
    kind: prior ? 'prior_history' : undefined,
    ts: message.ts,
    rateLimit: isRateLimitWait(message.rate_limit) ? message.rate_limit : undefined,
    fatalConfigError: message.fatal_config_error === true,
    persona: typeof message.persona === 'string' ? message.persona : undefined,
  }
}

/** Post-login return path for the Django session gate (rooted, same-origin). */
export function chatLoginNext(searchParams: URLSearchParams): string {
  const qs = searchParams.toString()
  return qs ? `/chat?${qs}` : '/chat'
}

export function chatLoginHref(searchParams: URLSearchParams): string {
  return `/accounts/login/?next=${encodeURIComponent(chatLoginNext(searchParams))}`
}
