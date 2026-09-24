/**
 * ADR-017 PR-3 / REQ-925 — the whole-SPA multiplex websocket (#1118).
 *
 * One socket for the entire app instead of one per mounted chat. Sessions
 * are **sticky per conversation**: switching agents unsubscribes the old
 * chat but its server-side worker keeps streaming, so an in-flight turn on
 * agent A still arrives (tagged `spa.frame`) while you read agent B. This
 * is the root fix for "avatar animation stops when you click away".
 *
 * Wire protocol (see src/swarm/spa_multiplex.py):
 *   client → {kind: 'subscribe'|'unsubscribe'|'chat.send', conversationId, ...}
 *   server → {kind: 'spa.frame'|'spa.subscribed'|'spa.error', conversationId, data?}
 *
 * Delivery to listeners is synchronous-in-order per event; reconnect
 * replays `subscribe` for every live conversation so sticky sessions are
 * re-adopted transparently.
 */
import { parseChatWsMessage, type ChatWsEvent } from './chatWs'
import { MAX_AUTO_RECONNECT_ATTEMPTS, WS_AUTH_REQUIRED_CODE, reconnectBackoffMs } from './chatReconnect'

export type SpaFrame = { kind: 'spa.frame'; conversationId: string; data: unknown }
export type SpaEnvelope =
  | SpaFrame
  | { kind: 'spa.subscribed'; conversationId: string }
  | { kind: 'spa.error'; conversationId: string; error: string; code?: number }

export type SpaListener = (event: ChatWsEvent, conversationId: string) => void
export type SpaStatusListener = (status: SpaStatus) => void
/** Sees every tagged frame crossing the socket — conversation-blind. */
export type SpaTapListener = (event: ChatWsEvent, conversationId: string) => void

export type SpaStatus = 'connecting' | 'open' | 'closed' | 'failed'

export interface SpaSubscription {
  /** Stop listening; the underlying socket stays until the page unloads. */
  release: () => void
}

interface Registry {
  socket: WebSocket | null
  /** conversationId → subscription count (live chat mounts). */
  subscriptions: Map<string, number>
  listeners: Map<string, Set<SpaListener>>
  statusListeners: Set<SpaStatusListener>
  taps: Set<SpaTapListener>
  errorListeners: Map<string, Set<SpaErrorListener>>
  /** conversationId → blueprint, replayed on reconnect. */
  blueprints: Map<string, string>
  status: SpaStatus
  backoffAttempt: number
  reconnectTimer: ReturnType<typeof setTimeout> | null
  intentionalClose: boolean
  /** Close code of the most recent socket close (4401 = auth rejected). */
  lastCloseCode: number | null
  /** Whether the current socket ever reached open (disconnect vs unreachable). */
  sawOpen: boolean
}

const registry: Registry = {
  socket: null,
  subscriptions: new Map(),
  listeners: new Map(),
  statusListeners: new Set(),
  taps: new Set(),
  errorListeners: new Map(),
  blueprints: new Map(),
  status: 'closed',
  backoffAttempt: 0,
  reconnectTimer: null,
  intentionalClose: false,
  lastCloseCode: null,
  sawOpen: false,
}

// Test seam: the module registry is replaced wholesale between tests.
export function resetSpaSocketForTests(): void {
  if (registry.reconnectTimer) clearTimeout(registry.reconnectTimer)
  if (registry.socket) {
    registry.intentionalClose = true
    try {
      registry.socket.close()
    } catch {
      /* already closed */
    }
  }
  registry.socket = null
  registry.subscriptions.clear()
  registry.listeners.clear()
  registry.statusListeners.clear()
  registry.taps.clear()
  registry.errorListeners.clear()
  registry.blueprints.clear()
  registry.status = 'closed'
  registry.backoffAttempt = 0
  registry.reconnectTimer = null
  registry.intentionalClose = false
  registry.lastCloseCode = null
}

export function spaStatus(): SpaStatus {
  return registry.status
}

export function onSpaStatus(listener: SpaStatusListener): SpaSubscription {
  registry.statusListeners.add(listener)
  return { release: () => registry.statusListeners.delete(listener) }
}

/**
 * Conversation-blind tap: every parsed `spa.frame` on the socket, regardless
 * of which conversation it belongs to. This is how the global turn store
 * sees background chats' bookends (#1118) without subscribing junk sessions.
 */
export function onSpaFrame(listener: SpaTapListener): SpaSubscription {
  registry.taps.add(listener)
  return { release: () => registry.taps.delete(listener) }
}

/** Error-envelope listener for one conversation (spa.error frames). */
export type SpaErrorListener = (error: string, code: number | null) => void

/** Subscribe to `spa.error` envelopes addressed to one conversation. */
export function onSpaConversationError(
  conversationId: string,
  listener: SpaErrorListener,
): SpaSubscription {
  const set = registry.errorListeners.get(conversationId) ?? new Set()
  set.add(listener)
  registry.errorListeners.set(conversationId, set)
  return {
    release: () => {
      const current = registry.errorListeners.get(conversationId)
      current?.delete(listener)
      if (current && current.size === 0) registry.errorListeners.delete(conversationId)
    },
  }
}

/** Close code of the most recent socket close — 4401 means auth rejected. */
export function spaLastCloseCode(): number | null {
  return registry.lastCloseCode
}

export function activeSpaConversations(): string[] {
  return [...registry.subscriptions.keys()]
}

function setStatus(next: SpaStatus): void {
  registry.status = next
  for (const listener of registry.statusListeners) listener(next)
}

export function buildSpaWsUrl(): string {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${window.location.host}/ws/spa/`
}

function nextBackoffMs(): number {
  const attempt = registry.backoffAttempt
  registry.backoffAttempt += 1
  return reconnectBackoffMs(attempt)
}

function ensureSocket(): WebSocket {
  if (
    registry.socket &&
    (registry.socket.readyState === WebSocket.OPEN || registry.socket.readyState === WebSocket.CONNECTING)
  ) {
    return registry.socket
  }
  registry.intentionalClose = false
  registry.sawOpen = false
  setStatus('connecting')
  let ws: WebSocket
  try {
    ws = new WebSocket(buildSpaWsUrl())
  } catch {
    // Constructor can throw (mocked sockets, sandboxed environments). Mirror
    // the legacy hook's contract: fail fast, then retry on the backoff clock
    // (first retry ≈1s — #334 pins the timer being cleared on unmount).
    setStatus('failed')
    const delay = nextBackoffMs()
    registry.reconnectTimer = setTimeout(() => {
      registry.reconnectTimer = null
      if (registry.subscriptions.size > 0) ensureSocket()
    }, delay)
    return null as unknown as WebSocket
  }
  registry.socket = ws

  ws.onopen = () => {
    registry.backoffAttempt = 0
    registry.sawOpen = true
    setStatus('open')
    // Re-adopt every sticky session this tab still holds.
    for (const conversationId of registry.subscriptions.keys()) {
      ws.send(
        JSON.stringify({ kind: 'subscribe', conversationId, blueprint: registry.blueprints.get(conversationId) }),
      )
    }
  }

  ws.onmessage = (event: MessageEvent) => {
    if (typeof event.data !== 'string') return
    let envelope: SpaEnvelope | null = null
    try {
      const parsed = JSON.parse(event.data) as Partial<SpaEnvelope>
      if (parsed && typeof parsed === 'object' && typeof parsed.kind === 'string') {
        envelope = parsed as SpaEnvelope
      }
    } catch {
      /* not JSON */
    }
    if (!envelope) {
      // Legacy-frame fallback (test harnesses + future server drift): a
      // bare frame with no mux envelope is treated as belonging to the
      // single subscribed conversation, if exactly one is mounted.
      if (registry.subscriptions.size === 1) {
        const [conversationId] = registry.subscriptions.keys()
        const chatEvent = parseChatWsMessage(event.data)
        for (const tap of registry.taps) tap(chatEvent, conversationId)
        for (const listener of registry.listeners.get(conversationId) ?? []) {
          listener(chatEvent, conversationId)
        }
      }
      return
    }
    if (envelope.kind === 'spa.frame') {
      const chatEvent = parseChatWsMessage(
        typeof envelope.data === 'string' ? envelope.data : JSON.stringify(envelope.data),
      )
      for (const tap of registry.taps) tap(chatEvent, envelope.conversationId)
      for (const listener of registry.listeners.get(envelope.conversationId) ?? []) {
        listener(chatEvent, envelope.conversationId)
      }
    } else if (envelope.kind === 'spa.error') {
      const code = typeof envelope.code === 'number' ? envelope.code : null
      for (const listener of registry.errorListeners.get(envelope.conversationId) ?? []) {
        listener(envelope.error, code)
      }
    }
  }

  ws.onclose = (event: CloseEvent) => {
    registry.socket = null
    registry.lastCloseCode = typeof event?.code === 'number' ? event.code : null
    setStatus(registry.intentionalClose || registry.sawOpen ? 'closed' : 'failed')
    if (registry.intentionalClose) return
    // Auth gate: the server closed with 4401 (session required). No auto
    // hammering — the Sign-in CTA drives reconnection, as in the legacy hook.
    if (typeof event?.code === 'number' && event.code === WS_AUTH_REQUIRED_CODE) return
    if (registry.backoffAttempt >= MAX_AUTO_RECONNECT_ATTEMPTS) return
    const delay = nextBackoffMs()
    registry.reconnectTimer = setTimeout(() => {
      registry.reconnectTimer = null
      if (registry.subscriptions.size > 0) ensureSocket()
    }, delay)
  }

  ws.onerror = () => {
    /* onclose follows; backoff is handled there */
  }

  return ws
}

function sendEnvelope(payload: Record<string, unknown>): void {
  const ws = ensureSocket()
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload))
  }
  // CONNECTING: onopen replays subscriptions; chat frames sent before open
  // are re-driven by the caller's retry on `spaStatus()`.
}

/** Mount a chat: subscribe (once per conversation) + listen for its frames. */
export function subscribeSpa(
  conversationId: string,
  listener: SpaListener,
  blueprint?: string,
): SpaSubscription {
  const first = !registry.subscriptions.has(conversationId)
  registry.subscriptions.set(conversationId, (registry.subscriptions.get(conversationId) ?? 0) + 1)
  if (blueprint) registry.blueprints.set(conversationId, blueprint)
  let listeners = registry.listeners.get(conversationId)
  if (!listeners) {
    listeners = new Set()
    registry.listeners.set(conversationId, listeners)
  }
  listeners.add(listener)
  if (first) sendEnvelope({ kind: 'subscribe', conversationId, blueprint })

  return {
    release: () => {
      const set = registry.listeners.get(conversationId)
      set?.delete(listener)
      const count = (registry.subscriptions.get(conversationId) ?? 1) - 1
      if (count <= 0) {
        registry.subscriptions.delete(conversationId)
        registry.listeners.delete(conversationId)
        // Sticky by design: the server session outlives the subscription so
        // background turns keep streaming (#1118). No unsubscribe is sent —
        // the tab keeps adopting the session on reconnect.
        return
      }
      registry.subscriptions.set(conversationId, count)
    },
  }
}

/** Send a legacy chat frame to one conversation through the mux. */
export function sendSpaChat(conversationId: string, frameJson: string): void {
  let parsed: Record<string, unknown> = {}
  try {
    parsed = JSON.parse(frameJson) as Record<string, unknown>
  } catch {
    return
  }
  sendEnvelope({ kind: 'chat.send', conversationId, ...parsed })
}

/** Best-effort: true when the mux socket is open and ready for sends. */
export function spaReady(): boolean {
  return registry.socket?.readyState === WebSocket.OPEN
}
