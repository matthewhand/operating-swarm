/**
 * #1168 — pending-send watchdog.
 *
 * The optimistic user echo (#1149) renders before the server acknowledges.
 * If the frame never reached the server (dead socket, restart race), the row
 * must NOT hang as "pending" forever: this watchdog fails it fast, visibly,
 * and offers a resend. Two independent detection layers:
 *
 * 1. **Send-time gate** — `assertSendable()` reports a dead socket BEFORE the
 *    echo renders, so the composer can toast immediately.
 * 2. **Grace watchdog** — after a send, if neither `user_echo` nor
 *    `assistant_start` (the first server bookends) arrives within
 *    `PENDING_SEND_GRACE_MS`, every still-pending row is marked
 *    `sendFailed: true` and a resend is offered. When the socket reopens the
 *    watchdog rearms, so the failure state also covers a reconnect that
 *    never produced a turn.
 */

import type { ChatMessage } from '../features/chat/chatMessages'

/** Time to wait for server confirmation before declaring the send lost. */
export const PENDING_SEND_GRACE_MS = 6_000

/** Marker for an optimistic row the server never confirmed. */
export interface SendFailedFields {
  pending?: boolean
  sendFailed?: boolean
}

/** True when the row is an optimistic echo still awaiting confirmation. */
export function isPendingEcho(message: ChatMessage): boolean {
  return message.role === 'user' && message.pending === true && !message.sendFailed
}

/** True when the row was declared lost and is awaiting user action. */
export function isSendFailed(message: ChatMessage): boolean {
  return message.role === 'user' && message.sendFailed === true
}

/**
 * Fails every still-pending echo in `messages` (immutably). Rows already
 * confirmed (pending cleared) or already failed are untouched.
 */
export function failStalePendingSends(messages: ChatMessage[]): ChatMessage[] {
  let changed = false
  const next = messages.map((m) => {
    if (isPendingEcho(m)) {
      changed = true
      return { ...m, sendFailed: true }
    }
    return m
  })
  return changed ? next : messages
}

/** Clears the failure marker (used by resend to restore the pending state). */
export function restorePendingSend(messages: ChatMessage[], key: string): ChatMessage[] {
  return messages.map((m) =>
    m.key === key && m.sendFailed ? { ...m, sendFailed: false, pending: true } : m,
  )
}
