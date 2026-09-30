/**
 * #1729 — the Herdr status websocket client.
 *
 * Herdr seat status rides its **own** push-only socket
 * (`/ws/herdr-status/`, `src/swarm/herdr_status_ws.py`), not the SPA
 * multiplex. The multiplex is a strict per-conversation transport whose
 * contract is that every frame is a reply to something the client asked for;
 * unsolicited seat status would interleave frames nobody requested, and
 * opening a *chat* socket on a page with no chat is its own kind of lie.
 *
 * One module-level socket, refcounted by subscriber, so N mounted surfaces
 * cost one connection. Reconnect follows the same shape as
 * `lib/spaSocket` — bounded attempts, backoff, and a deliberate close that
 * does not retry — because a status feed that reconnects forever against a
 * server the user just logged out of is worse than a silent one.
 */

import { parseHerdrStatusFrame, type HerdrStatusFrame } from './herdrStatus'
import { MAX_AUTO_RECONNECT_ATTEMPTS, WS_AUTH_REQUIRED_CODE, reconnectBackoffMs } from './chatReconnect'

export type HerdrStatusListener = (frame: HerdrStatusFrame) => void
export type HerdrStatusState = 'idle' | 'connecting' | 'open' | 'closed' | 'failed'
export type HerdrStatusSubscription = { release: () => void }

interface Registry {
  socket: WebSocket | null
  listeners: Set<HerdrStatusListener>
  state: HerdrStatusState
  stateListeners: Set<(state: HerdrStatusState) => void>
  backoffAttempt: number
  reconnectTimer: ReturnType<typeof setTimeout> | null
  intentionalClose: boolean
  lastCloseCode: number | null
}

const registry: Registry = {
  socket: null,
  listeners: new Set(),
  state: 'idle',
  stateListeners: new Set(),
  backoffAttempt: 0,
  reconnectTimer: null,
  intentionalClose: false,
  lastCloseCode: null,
}

function setState(next: HerdrStatusState): void {
  registry.state = next
  for (const listener of registry.stateListeners) {
    try {
      listener(next)
    } catch {
      /* ignore listener errors */
    }
  }
}

export function herdrStatusSocketState(): HerdrStatusState {
  return registry.state
}

export function onHerdrStatusState(
  listener: (state: HerdrStatusState) => void,
): HerdrStatusSubscription {
  registry.stateListeners.add(listener)
  return { release: () => registry.stateListeners.delete(listener) }
}

export function buildHerdrStatusWsUrl(): string {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${window.location.host}/ws/herdr-status/`
}

function nextBackoffMs(): number {
  const attempt = registry.backoffAttempt
  registry.backoffAttempt += 1
  return reconnectBackoffMs(attempt)
}

function clearReconnectTimer(): void {
  if (registry.reconnectTimer !== null) {
    clearTimeout(registry.reconnectTimer)
    registry.reconnectTimer = null
  }
}

function ensureSocket(): void {
  if (registry.listeners.size === 0) return
  if (
    registry.socket &&
    (registry.socket.readyState === WebSocket.OPEN ||
      registry.socket.readyState === WebSocket.CONNECTING)
  ) {
    return
  }
  registry.intentionalClose = false
  setState('connecting')
  let socket: WebSocket
  try {
    socket = new WebSocket(buildHerdrStatusWsUrl())
  } catch {
    // A constructor can throw (sandboxed environment, blocked socket). Fail
    // fast, then retry on the backoff clock, and cap it: a status feed that
    // reconnects forever is worse than a silent one.
    setState('failed')
    if (registry.backoffAttempt < MAX_AUTO_RECONNECT_ATTEMPTS) {
      registry.reconnectTimer = setTimeout(() => {
        registry.reconnectTimer = null
        ensureSocket()
      }, nextBackoffMs())
    }
    return
  }
  registry.socket = socket

  socket.onopen = () => {
    registry.backoffAttempt = 0
    setState('open')
  }
  socket.onmessage = (event: MessageEvent) => {
    if (typeof event.data !== 'string') return
    const frame = parseHerdrStatusFrame(safeParse(event.data))
    // A frame we cannot vouch for is dropped, not guessed at.
    if (!frame) return
    for (const listener of registry.listeners) {
      try {
        listener(frame)
      } catch {
        /* one bad listener must not starve the others */
      }
    }
  }
  socket.onclose = (event: CloseEvent) => {
    registry.socket = null
    registry.lastCloseCode = typeof event?.code === 'number' ? event.code : null
    setState(registry.intentionalClose ? 'closed' : 'failed')
    if (registry.intentionalClose) return
    // Auth gate: 4401 means the session is gone. The Sign-in CTA drives
    // reconnection; hammering a rejected socket is not helpful.
    if (registry.lastCloseCode === WS_AUTH_REQUIRED_CODE) return
    if (registry.backoffAttempt >= MAX_AUTO_RECONNECT_ATTEMPTS) return
    registry.reconnectTimer = setTimeout(() => {
      registry.reconnectTimer = null
      ensureSocket()
    }, nextBackoffMs())
  }
  socket.onerror = () => {
    /* onclose follows; backoff is handled there */
  }
}

function safeParse(raw: string): unknown {
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

/**
 * Subscribe to seat status. The first subscriber opens the socket; the last
 * release closes it, so an unmounted app stops reconnecting.
 */
export function subscribeHerdrStatusFeed(
  listener: HerdrStatusListener,
): HerdrStatusSubscription {
  registry.listeners.add(listener)
  ensureSocket()
  let released = false
  return {
    release: () => {
      if (released) return
      released = true
      registry.listeners.delete(listener)
      if (registry.listeners.size > 0) return
      clearReconnectTimer()
      registry.intentionalClose = true
      try {
        registry.socket?.close()
      } catch {
        /* already closed */
      }
      registry.socket = null
      registry.backoffAttempt = 0
      setState('closed')
    },
  }
}

/** Test seam: the module registry is process-global by design. */
export function resetHerdrStatusSocketForTests(): void {
  clearReconnectTimer()
  registry.intentionalClose = true
  try {
    registry.socket?.close()
  } catch {
    /* already closed */
  }
  registry.socket = null
  registry.listeners.clear()
  registry.stateListeners.clear()
  registry.state = 'idle'
  registry.backoffAttempt = 0
  registry.intentionalClose = false
  registry.lastCloseCode = null
}
