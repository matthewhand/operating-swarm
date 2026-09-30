/**
 * #1783 — one throttle gate, shared by both health polls.
 *
 * A 429 from the DRF write throttle is not an error to shrug off and retry
 * next tick: the health polls are the *only* recurring writers in the app, so
 * "next tick" is the queue that keeps the window shut. The symptom was a
 * `Too many requests — the server is busy. Please try again in 2s.` toast
 * every 60s, i.e. a poll that knows it is being throttled and digs anyway.
 *
 * So: a poll that gets a 429 stops probing until the server's own hint says the
 * window is free. Nothing is queued in the meantime — the last verdict stays on
 * screen, which is honest, and a fresh tick costs zero requests until then.
 *
 * The wait, in order of preference:
 *  1. `Retry-After` from the response, via the typed `ApiThrottleError` that
 *     `classifyApiError` already builds (#581) — the server's real number,
 *     honoured as sent. Capping it would be the client overruling the server
 *     about its own quota, which is the thing that got it throttled.
 *  2. the 2s the server's own message quotes, doubling per consecutive 429 up
 *     to :data:`MAX_THROTTLE_WAIT_MS`. A client that keeps getting throttled
 *     after waiting the advertised time is the definition of a busy loop, and
 *     the guess needs a ceiling so a poll still comes back on its own.
 * A single successful request clears the streak and the pause: the window is
 * demonstrably free, so there is nothing left to be polite about.
 *
 * Both `remoteHealth` and `seatHealth` hold one of these. It is a plain object
 * with an injectable clock so the tests can drive a 60s tick without a timer.
 */
import { isThrottleError } from './api'

/** The wait the server quotes when it has no `Retry-After` to give. */
export const DEFAULT_THROTTLE_WAIT_MS = 2_000
/** Ceiling on the GUESSED backoff (see above). */
export const MAX_THROTTLE_WAIT_MS = 60_000

export interface ThrottleGate {
  /** Record a rejection. Returns the wait in ms (0 when it was not a 429). */
  note: (error: unknown, now?: number) => number
  /** A request landed: the window is free, so the streak and pause are over. */
  noteSuccess: () => void
  /** True while the gate is shut — a poll must not send. */
  paused: (now?: number) => boolean
  /** How much longer the gate stays shut (0 when open). */
  remainingMs: (now?: number) => number
}

export function createThrottleGate(): ThrottleGate {
  let pausedUntil = 0
  let consecutive = 0

  return {
    note(error: unknown, now = Date.now()): number {
      if (!isThrottleError(error)) return 0
      consecutive += 1
      const advertised = error.retryAfterSeconds * 1_000
      const wait =
        advertised > 0
          ? advertised
          : Math.min(DEFAULT_THROTTLE_WAIT_MS * 2 ** (consecutive - 1), MAX_THROTTLE_WAIT_MS)
      pausedUntil = now + wait
      return wait
    },
    noteSuccess(): void {
      consecutive = 0
      pausedUntil = 0
    },
    paused(now = Date.now()): boolean {
      return now < pausedUntil
    },
    remainingMs(now = Date.now()): number {
      return Math.max(0, pausedUntil - now)
    },
  }
}
