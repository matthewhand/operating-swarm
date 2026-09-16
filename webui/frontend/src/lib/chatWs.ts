import { parseContextUsage, type ContextUsage } from './contextUsage'
import { questionFromPayload, type DecisionQuestion } from './decisionQuestion'
import { parsePrOpened, type PrOpenedEvent } from './prOpened'
import {
  isRateLimitWait,
  parseRateLimitWaitFromDataset,
  type RateLimitWait,
} from './providerRateLimits'
import { parseSuggestions } from './suggestions'
import { parseTeammateTask, type TeammateTaskEvent } from './teammateTask'
import { parseSubagentFanOut, type SubagentFanOutData } from './subagentFanOut'

/**
 * Client for the Django Channels chat websocket.
 *
 * Protocol (verified against src/swarm/consumers.py DjangoChatConsumer and
 * src/swarm/templates/chat.html / websocket_partials/*):
 *
 * - URL: ws(s)://<host>/ws/ai-demo/<conversation_id>/
 *   (the Django UI connects via HTMx: ws-connect="/ws/ai-demo/{{ conversation.id }}/")
 *   An optional ?blueprint=<id> query param sets a connection-level default
 *   blueprint on the server.
 * - Client -> server: JSON text frames: {"message": "<user text>"} with an
 *   optional "blueprint": "<id>" field selecting which discovered blueprint
 *   answers (per-message field overrides the URL default; omitting both
 *   falls back to the server-configured model). An optional "params" object
 *   is forwarded to the blueprint (e.g. {cli: "grok"} for cli_agent).
 * - Server -> client: HTML partials with HTMx out-of-band swap attributes:
 *   1. user echo:        <div id="message-list" hx-swap-oob="beforeend">
 *                          <div class="user-message ...">{text}</div></div>
 *   2. assistant start:  <div id="message-list" hx-swap-oob="beforeend">
 *                          <div id="message-response-<hex>" class="assistant-message ..."></div></div>
 *   3. stream chunk:     <div hx-swap-oob="beforeend:#message-response-<hex>">{chunk}</div>
 *   4. final message:    <div id="message-response-<hex>" hx-swap-oob="true" ...>{full text}</div>
 *
 * The consumer requires an authenticated Django **session cookie**
 * (AuthMiddlewareStack). REST API bearer tokens do not authenticate
 * websockets. Anonymous connects are accept-then-closed with code 4401.
 * The server must run under ASGI with Channels for the /ws/ route to exist.
 */

export type ToolStatus = 'running' | 'allowed' | 'done' | 'denied' | 'error'

export type ChatWsEvent =
  | { kind: 'user_echo'; text: string }
  | { kind: 'assistant_start'; id: string }
  | { kind: 'assistant_chunk'; id: string; text: string }
  | { kind: 'assistant_final'; id: string; text: string }
  | {
      kind: 'tool_status'
      id: string
      name: string
      status: ToolStatus
      agentId?: string
    }
  | {
      kind: 'tool_approval'
      id: string
      name: string
      agentId?: string
    }
  | {
      kind: 'user_question'
      question: DecisionQuestion
      agentId?: string
    }
  | {
      kind: 'status'
      text: string
      rateLimit?: RateLimitWait
    }
  | { kind: 'pr_opened'; event: PrOpenedEvent }
  | { kind: 'teammate_task'; event: TeammateTaskEvent }
  | { kind: 'subagent_fan_out'; event: SubagentFanOutData }
  | { kind: 'spa_hello'; spaVersion: string }
  | { kind: 'suggestions'; suggestions: string[] }
  | { kind: 'context_usage'; usage: ContextUsage }
  | {
      kind: 'interbot_hop'
      id: string
      agentId: string
      name: string
      pending: boolean
    }
  | { kind: 'unknown'; raw: string }

/** Keys-and-size summary for unknown frames — never log the raw payload. */
export function summarizeUnknownWsFrame(raw: string): string {
  const bytes = new TextEncoder().encode(raw).length
  let keys = ''
  try {
    const parsed: unknown = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const names = Object.keys(parsed as Record<string, unknown>).slice(0, 8)
      if (names.length) keys = `; keys=${names.join(',')}`
    }
  } catch {
    // HTML / non-JSON
  }
  return `kind=unknown; bytes=${bytes}${keys}`
}

const OOB_CHUNK_PREFIX = 'beforeend:#'
const ASSISTANT_ID_PREFIX = 'message-response-'

export function buildChatWsUrl(
  conversationId: string,
  blueprintId?: string,
): string {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const base = `${scheme}://${window.location.host}/ws/ai-demo/${encodeURIComponent(conversationId)}/`
  return blueprintId
    ? `${base}?blueprint=${encodeURIComponent(blueprintId)}`
    : base
}

/** Optional per-message params (team target, CLI, …) forwarded to the consumer. */
export type ChatWsParams = Record<string, unknown>

/**
 * Merge per-turn WS params. Later objects win on key conflicts so an explicit
 * CLI dropdown (`cli` / `failover: false`) is not overwritten by inference seats.
 */
export function mergeChatSendParams(
  ...parts: Array<ChatWsParams | undefined | null>
): ChatWsParams | undefined {
  const merged: ChatWsParams = {}
  for (const part of parts) {
    if (!part) continue
    Object.assign(merged, part)
  }
  return Object.keys(merged).length > 0 ? merged : undefined
}

/** cli_agent dropdown send params: try this CLI only (issue #99). */
export function cliAgentChatParams(cli: string, model?: string): ChatWsParams {
  const params: ChatWsParams = { cli, failover: false }
  const trimmed = (model ?? '').trim()
  if (trimmed && trimmed !== 'default') params.model = trimmed
  return params
}

/** Build the JSON frame sent to DjangoChatConsumer.receive(). */
export function buildChatWsFrame(
  message: string,
  blueprintId?: string,
  params?: ChatWsParams,
  attachments?: string[],
): string {
  const frame: Record<string, unknown> = { message }
  if (blueprintId) frame.blueprint = blueprintId
  if (params && Object.keys(params).length > 0) frame.params = params
  if (attachments && attachments.length > 0) frame.attachments = attachments
  return JSON.stringify(frame)
}

export function buildToolDecisionFrame(
  id: string,
  decision: 'allow' | 'always' | 'deny',
): string {
  return JSON.stringify({ type: 'tool_decision', id, decision })
}

/** Resume an in-flight ``ask_user`` tool (issue #221). */
export function buildQuestionAnswerFrame(id: string, answer: string): string {
  return JSON.stringify({ type: 'question_answer', id, answer })
}

/** Build the JSON frame that edits an existing transcript turn (REQ-49). */
export function buildChatWsEditFrame(index: number, content: string): string {
  return JSON.stringify({ edit: { index, content } })
}

/** #198: ask the server to interrupt the turn in flight (enter-to-interrupt). */
export function buildCancelTurnFrame(): string {
  return JSON.stringify({ type: 'cancel_turn' })
}

export function newConversationId(): string {
  try {
    return crypto.randomUUID()
  } catch {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  }
}

function parseInterbotHop(el: Element): ChatWsEvent {
  return {
    kind: 'interbot_hop',
    id: el.id,
    agentId: el.getAttribute('data-agent-id') ?? '',
    name: el.getAttribute('data-agent-name') ?? '',
    pending: el.getAttribute('data-pending') === 'true',
  }
}

const TOOL_STATUSES = new Set<ToolStatus>(['running', 'allowed', 'done', 'denied', 'error'])

function parseToolJsonFrame(raw: string): ChatWsEvent | null {
  const trimmed = raw.trim()
  if (!trimmed.startsWith('{')) return null
  try {
    const payload = JSON.parse(trimmed) as Record<string, unknown>
    const type = String(payload.type || '')
    const id = String(payload.id || '')
    const name = String(payload.name || '')
    if (type === 'tool_status' && id && name) {
      const status = String(payload.status || '') as ToolStatus
      if (!TOOL_STATUSES.has(status)) return { kind: 'unknown', raw }
      return {
        kind: 'tool_status',
        id,
        name,
        status,
        agentId: payload.agent_id ? String(payload.agent_id) : undefined,
      }
    }
    if (type === 'tool_approval' && id && name) {
      return {
        kind: 'tool_approval',
        id,
        name,
        agentId: payload.agent_id ? String(payload.agent_id) : undefined,
      }
    }
    if (type === 'user_question') {
      const question = questionFromPayload(payload)
      if (question) {
        return {
          kind: 'user_question',
          question,
          agentId: payload.agent_id ? String(payload.agent_id) : undefined,
        }
      }
    }
    if (type === 'pr_opened') {
      const event = parsePrOpened(payload)
      if (event) return { kind: 'pr_opened', event }
    }
    if (type === 'teammate_task') {
      if (Array.isArray(payload.subagents) && payload.subagents.length > 0) {
        const fanOut = parseSubagentFanOut(payload)
        if (fanOut) return { kind: 'subagent_fan_out', event: fanOut }
      }
      const event = parseTeammateTask(payload)
      if (event) return { kind: 'teammate_task', event }
    }
    if (type === 'subagent_fan_out') {
      const event = parseSubagentFanOut(payload)
      if (event) return { kind: 'subagent_fan_out', event }
    }
    if (type === 'spa_hello') {
      const spaVersion = String(payload.spa_version || '').trim()
      if (!spaVersion) return { kind: 'unknown', raw }
      return { kind: 'spa_hello', spaVersion }
    }
    if (type === 'turn_cancelled') {
      // #198: ack for cancel_turn — styled as a status line in the transcript.
      return { kind: 'status', text: 'Interrupted — queued message promoted.' }
    }
    if (type === 'suggestions') {
      const suggestions = parseSuggestions(payload)
      return { kind: 'suggestions', suggestions }
    }
    if (type === 'context_usage') {
      const usage = parseContextUsage(payload)
      if (!usage) return { kind: 'unknown', raw }
      return { kind: 'context_usage', usage }
    }
    if (type === 'rate_limit_wait' || payload.object === 'open_swarm.rate_limit_wait') {
      if (isRateLimitWait(payload)) {
        return {
          kind: 'status',
          text: String(payload.text || ''),
          rateLimit: payload,
        }
      }
    }
  } catch {
    return null
  }
  return null
}

/** Parse one HTMx HTML partial frame (or JSON tool event) into a typed event. */
export function parseChatWsMessage(raw: string): ChatWsEvent {
  const jsonEvent = parseToolJsonFrame(raw)
  if (jsonEvent) return jsonEvent

  let root: Element | null = null
  try {
    const doc = new DOMParser().parseFromString(raw, 'text/html')
    root = doc.body.firstElementChild
  } catch {
    return { kind: 'unknown', raw }
  }
  if (!root) {
    return { kind: 'unknown', raw }
  }

  const oob = root.getAttribute('hx-swap-oob') ?? ''

  // 3. Streaming chunk appended to an assistant message container.
  if (oob.startsWith(OOB_CHUNK_PREFIX)) {
    return {
      kind: 'assistant_chunk',
      id: oob.slice(OOB_CHUNK_PREFIX.length),
      text: root.textContent ?? '',
    }
  }

  // 1 + 2. Appends to the global #message-list.
  if (root.id === 'message-list' && oob === 'beforeend') {
    const child = root.firstElementChild
    if (child?.classList.contains('user-message')) {
      return { kind: 'user_echo', text: (child.textContent ?? '').trim() }
    }
    if (child?.classList.contains('chat-status-line')) {
      return {
        kind: 'status',
        text: (child.textContent ?? '').trim(),
        rateLimit: parseRateLimitWaitFromDataset(child),
      }
    }
    if (child?.classList.contains('os-interbot-hop')) {
      return parseInterbotHop(child)
    }
    if (child?.id.startsWith(ASSISTANT_ID_PREFIX)) {
      return { kind: 'assistant_start', id: child.id }
    }
    return { kind: 'unknown', raw }
  }

  if (root.classList.contains('os-interbot-hop')) {
    return parseInterbotHop(root)
  }

  // 4. Final replacement of the assistant message container.
  if (root.id.startsWith(ASSISTANT_ID_PREFIX) && oob === 'true') {
    return {
      kind: 'assistant_final',
      id: root.id,
      text: (root.textContent ?? '').trim(),
    }
  }

  return { kind: 'unknown', raw }
}
