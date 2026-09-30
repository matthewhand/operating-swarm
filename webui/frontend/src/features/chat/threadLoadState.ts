/**
 * Thread identity + thread-load presentation for the chat transcript.
 *
 * Two jobs, both previously duplicated across ChatPage's three inline
 * `` `remote-${remote}${session ? `-${session}` : ''}` `` templates:
 *
 * 1. ONE derivation for a remote seat's conversation id. The first-mount
 *    ``useState`` initialiser, the ``threadKey`` used for rendering, and the
 *    hydrate effect's request key all call :func:`remoteThreadId`, so "the id
 *    derived on remount" cannot drift from "the id derived on first mount" —
 *    a drift that loads an empty thread while the rows sit under the id the UI
 *    stopped asking for. The params are trimmed: an untrimmed
 *    ``?session=`` (a lone space) used to mint ``remote-<remote>- `` and
 *    address a conversation that does not exist.
 *
 * 2. ONE classification of what the transcript should show while a thread
 *    loads. An empty render is ambiguous — it reads as "your messages are
 *    gone" — so loading is its own state: a dimmed, non-interactive copy of
 *    whatever is already on screen (:data:`ThreadLoadPhase` ``loading-stale``)
 *    or an explicit loading state when there is nothing to show
 *    (``loading-empty``). A failed load is ``error``, never ``empty``.
 */

/** Conversation id for a ``?remote=<name>`` seat, optionally session-pinned. */
export function remoteThreadId(remote: string, session?: string | null): string {
  const r = (remote || '').trim()
  const s = (session || '').trim()
  return s ? `remote-${r}-${s}` : `remote-${r}`
}

export type ThreadLoadPhase =
  /** No rows yet and the fetch is still open — show loading, not emptiness. */
  | 'loading-empty'
  /** Rows on screen that the in-flight fetch has not confirmed yet. */
  | 'loading-stale'
  /** The fetch failed. Say so; an error is not an empty thread. */
  | 'error'
  /** The fetch resolved with genuinely no rows. */
  | 'empty'
  /** The fetch resolved; the rows on screen are live. */
  | 'ready'

export interface ThreadLoadState {
  threadReady: boolean
  messageCount: number
  hydrateError?: string | null
}

/**
 * Classify the transcript's load state.
 *
 * ``threadReady`` is the page's "the hydrate request has settled" flag, so an
 * unready thread with rows on screen is exactly the cached-while-loading case:
 * the rows are a previous copy, not live data.
 */
export function threadLoadPhase({
  threadReady,
  messageCount,
  hydrateError,
}: ThreadLoadState): ThreadLoadPhase {
  const hasRows = messageCount > 0
  if (!threadReady) return hasRows ? 'loading-stale' : 'loading-empty'
  if (hydrateError) return 'error'
  return hasRows ? 'ready' : 'empty'
}

/** Spoken/announced while a thread is loading with nothing cached to show. */
export const THREAD_LOADING_LABEL = 'Loading this conversation'
/** Spoken/announced while a dimmed previous copy is on screen. */
export const THREAD_STALE_LABEL =
  'Showing the previous copy of this conversation while it loads. Controls are disabled until it loads.'
