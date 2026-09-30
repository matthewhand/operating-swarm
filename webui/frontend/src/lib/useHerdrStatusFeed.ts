/**
 * #1729 — mount the Herdr status feed for the whole SPA.
 *
 * One subscription on the dedicated status socket
 * (`/ws/herdr-status/`, `src/swarm/herdr_status_ws.py`) feeds every seat's
 * status, whether or not that seat's chat is open. That is the whole point: a
 * status that only arrives while its chat happens to be mounted is the silent
 * UI this replaces.
 *
 * The hook is mounted in `App` rather than in the rail so the feed is armed on
 * the chat-free routes too — the rail is collapsed on mobile, and the settings
 * sheet replaces the whole shell.
 *
 * Home is `lib/` beside `useAvatarTheme`, the same shape: a hook that binds an
 * external stream to React. It deliberately does **not** open a
 * `features/herdr/` package — #1030 requires every such package to be claimed
 * by a source-surface pin, and this hook is the only thing that would live
 * there. One file in an existing home beats a package with one file in it.
 */

import { useEffect } from 'react'
import { subscribeHerdrStatusFeed } from './herdrStatusSocket'
import { applyHerdrStatusFrame } from './herdrStatus'

/** Subscribe to the Herdr status feed. Idempotent per mount; one socket. */
export function useHerdrStatusFeed(): void {
  useEffect(() => {
    // The socket layer validates and parses; this hook's only job is the fold
    // into the status store, which is where unread is written.
    const subscription = subscribeHerdrStatusFeed((frame) => {
      applyHerdrStatusFrame(frame)
    })
    return () => subscription.release()
  }, [])
}

export default useHerdrStatusFeed
