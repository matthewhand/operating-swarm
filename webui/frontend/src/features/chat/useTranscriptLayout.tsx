/**
 * #856 slice 18 — transcript layout & read-state effects, verbatim from
 * ChatPage.
 *
 * Composer-dock inset measuring (#743 family) + ResizeObservers, the
 * identity-title truncation probe (#678), unread-event listening (#96),
 * the scroll/new-divider/visibility read-marking effects, and the WS
 * toast/reconnect plumbing. All state and refs stay page-owned.
 */
import { useCallback, useEffect, useLayoutEffect, useRef } from 'react'
import type { RefObject } from 'react'
import { TOAST_KIND_WS_DISCONNECT, type Toast } from '../../components/DaisyUI'
import {
  isPinnedToTranscriptBottom,
  measureComposerDockInset,
  scrollTranscriptToBottom,
} from '../../lib/composerInset'
import { countableChatCount } from '../../lib/chatLog'
import { generationIsInFlight } from '../../lib/chatQueue'
import { saveLastRead } from '../../lib/chatLastRead'
import {
  loadUnreadAgentIds,
  markAgentRead,
  UNREAD_CHANGED_EVENT,
} from '../../lib/unreadAgents'
import type { ChatConnectionStatus } from '../../lib/chatConnection'
import type { ChatMessage } from './chatMessages'

export interface UseTranscriptLayoutOptions {
  messages: ChatMessage[]
  replyTarget: unknown
  input: string
  awaitingAssistant: boolean
  selectedAgentName: string
  workspaceSubtitle: string
  status: ChatConnectionStatus
  connectAttempt: number
  authRejected: boolean
  signInHref: string
  seatUnread: boolean
  activeChatAgentId: string
  conversationId: string
  composerInsetPx: number
  newBeforeKey: string | null
  bottomDockRef: RefObject<HTMLDivElement | null>
  scrollBoxRef: RefObject<HTMLDivElement | null>
  listEndRef: RefObject<HTMLDivElement | null>
  composerRef: RefObject<HTMLTextAreaElement | null>
  pinnedToBottomRef: { current: boolean }
  setComposerInsetPx: (value: number | ((prev: number) => number)) => void
  setTranscriptHeightPx: (value: number) => void
  setUnreadIds: (value: string[]) => void
  addToast: (toast: Omit<Toast, 'id'>) => void
  dismissByKind: (kind: string) => void
  reconnect: () => void
}

export function useTranscriptLayout(opts: UseTranscriptLayoutOptions) {
  const {
    messages,
    replyTarget,
    input,
    awaitingAssistant,
    selectedAgentName,
    workspaceSubtitle,
    status,
    connectAttempt,
    authRejected,
    signInHref,
    seatUnread,
    activeChatAgentId,
    conversationId,
    newBeforeKey,
    bottomDockRef,
    scrollBoxRef,
    setComposerInsetPx,
    setTranscriptHeightPx,
    listEndRef,
    composerRef,
    pinnedToBottomRef,
    composerInsetPx,
    setUnreadIds,
    addToast,
    dismissByKind,
    reconnect,
  } = opts
  const prevStatusRef = useRef<ChatConnectionStatus>('connecting')

  const applyComposerInset = useCallback(() => {
    const next = measureComposerDockInset(bottomDockRef.current)
    setComposerInsetPx((prev) => (prev === next ? prev : next))
  }, [])

  useLayoutEffect(() => {
    applyComposerInset()
  }, [applyComposerInset, messages, replyTarget, input])

  useLayoutEffect(() => {
    const dock = bottomDockRef.current
    if (!dock || typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(() => {
      applyComposerInset()
    })
    observer.observe(dock)
    return () => observer.disconnect()
  }, [applyComposerInset])

  useLayoutEffect(() => {
    const box = scrollBoxRef.current
    if (!box) return undefined
    const apply = () => setTranscriptHeightPx(box.clientHeight)
    apply()
    if (typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(apply)
    observer.observe(box)
    return () => observer.disconnect()
  }, [])

  // #678: gate the navbar name's fade on actual truncation. The mask must
  // not engage while the name fits — the header's other items are not greedy
  // (shrink-0 clusters aside, the identity card owns the remaining width).
  const identityTitleRef = useRef<HTMLHeadingElement | null>(null)
  useLayoutEffect(() => {
    const title = identityTitleRef.current
    if (!title) return undefined
    const apply = () => {
      const clipped = title.scrollWidth > title.clientWidth
      title.dataset.truncated = clipped ? 'true' : 'auto'
    }
    apply()
    if (typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(apply)
    observer.observe(title)
    return () => observer.disconnect()
  }, [selectedAgentName, workspaceSubtitle])

  useEffect(() => {
    const onUnread = () => setUnreadIds(loadUnreadAgentIds())
    window.addEventListener(UNREAD_CHANGED_EVENT, onUnread)
    window.addEventListener('storage', onUnread)
    return () => {
      window.removeEventListener(UNREAD_CHANGED_EVENT, onUnread)
      window.removeEventListener('storage', onUnread)
    }
  }, [])

  useEffect(() => {
    if (newBeforeKey) {
      const marker = scrollBoxRef.current?.querySelector('[data-testid="chat-new-divider"]')
      if (marker) {
        marker.scrollIntoView({ block: 'center', inline: 'nearest' })
        pinnedToBottomRef.current = false
        return
      }
    }
    if (pinnedToBottomRef.current) {
      scrollTranscriptToBottom(scrollBoxRef.current, listEndRef.current)
    }
  }, [messages, composerInsetPx, newBeforeKey, awaitingAssistant])

  useEffect(() => {
    if (!activeChatAgentId || seatUnread) return
    if (!pinnedToBottomRef.current) return
    // #96: a hidden tab never counts as reading the transcript.
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
    saveLastRead(activeChatAgentId, conversationId, countableChatCount(messages))
  }, [activeChatAgentId, conversationId, messages, seatUnread])

  // #96: returning to a visible tab while pinned at the bottom counts as
  // catching up — the scroll handler alone would miss it (no scroll event).
  useEffect(() => {
    const onVisibility = () => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
      if (!pinnedToBottomRef.current || !seatUnread || !activeChatAgentId) return
      setUnreadIds(markAgentRead(activeChatAgentId))
      saveLastRead(activeChatAgentId, conversationId, countableChatCount(messages))
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [seatUnread, activeChatAgentId, conversationId, messages])

  // #96: unread clears only when the seat is visible AND pinned to the
  // transcript bottom — not merely because a scroll happened.
  const handleTranscriptScroll = useCallback(
    (e: React.UIEvent<HTMLElement>) => {
      const atBottom = isPinnedToTranscriptBottom(e.currentTarget, composerInsetPx)
      pinnedToBottomRef.current = atBottom
      if (!atBottom || !seatUnread || !activeChatAgentId) return
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
      setUnreadIds(markAgentRead(activeChatAgentId))
      saveLastRead(activeChatAgentId, conversationId, countableChatCount(messages))
    },
    [composerInsetPx, seatUnread, activeChatAgentId, conversationId, messages],
  )

  useEffect(() => {
    const wasOpen = prevStatusRef.current === 'open'
    prevStatusRef.current = status
    if (status === 'open' && !wasOpen && connectAttempt > 0) {
      composerRef.current?.focus()
    }
  }, [status, connectAttempt])


  useEffect(() => {
    if (status === 'open') {
      dismissByKind(TOAST_KIND_WS_DISCONNECT)
      return
    }
    if (status !== 'failed' && status !== 'closed') return
    const title = authRejected
      ? 'Chat unavailable — sign in required'
      : status === 'failed'
        ? 'Chat websocket unreachable'
        : 'Chat disconnected'
    const detail = authRejected
      ? 'Live chat needs a Django session cookie. Sign in, then reconnect.'
      : status === 'failed'
        ? 'ASGI is not serving /ws/ or Origin does not match ALLOWED_HOSTS.'
        : 'The chat websocket closed. Message history is kept.'
    addToast({
      kind: TOAST_KIND_WS_DISCONNECT,
      type: 'error',
      title,
      message: (
        <span>
          {detail}{' '}
          {authRejected ? (
            <a href={signInHref} className="link">
              Sign in
            </a>
          ) : null}{' '}
          <button type="button" className="link" onClick={reconnect}>
            Reconnect
          </button>
        </span>
      ),
      position: 'bottom-right',
      sticky: true,
    })
  }, [status, authRejected, signInHref, addToast, dismissByKind, reconnect])


  // #595: one signal for the composer's trailing controls — the Stop button
  // swaps into the microphone's slot while a turn is in flight, so the row
  // keeps a constant control count and never shifts under the pointer.
  const composerBusy = status === 'open' && generationIsInFlight(messages, awaitingAssistant)

  return { handleTranscriptScroll, composerBusy, identityTitleRef }
}
