import { isValidHeaderSeatKey } from './seatRouting'
import { createContext, createElement, useContext, type ReactNode } from "react"

/**
 * #1445: the chat navbar is chat-route chrome. It must clear when the
 * foreground surface is not an active chat — Settings included — so a stale
 * remote/team identity (AnythingLLM) cannot sit on an unrelated page.
 *
 * Settings stays an overlay (chat remains mounted). The header hides in the
 * same render that opens the sheet. It stays mounted so the gear button can
 * take focus back when the sheet closes. A chat route with no seat id
 * (empty key or `api:`) does not show it either.
 */

let settingsSurface = false
const listeners = new Set<() => void>()

const ChatHeaderSuppressedContext = createContext(false)

/** `/`, `/chat`, and `/chat/*` are the only routes that own this header. */
export function isChatHeaderRoute(pathname: string): boolean {
  return pathname === "/" || pathname === "/chat" || pathname.startsWith("/chat/")
}

export function chatHeaderSuppressed(): boolean {
  return settingsSurface
}

export function setChatHeaderSuppressed(next: boolean): void {
  if (settingsSurface === next) return
  settingsSurface = next
  for (const listener of listeners) listener()
}

export function subscribeChatHeaderSurface(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/**
 * Chat-only header controls render only on a chat route that has a valid
 * active seat, and only while that chat is the foreground surface. Settings
 * (and any other caller that suppresses the surface) clears them even though
 * ChatPage stays mounted underneath. An empty key and `headerSeatKey({})`
 * (`api:`) are not seats.
 */
export function shouldShowChatHeader(
  pathname: string,
  suppressed: boolean = chatHeaderSuppressed(),
  seatKey: string = '',
): boolean {
  return isChatHeaderRoute(pathname) && !suppressed && isValidHeaderSeatKey(seatKey)
}

/** Test isolation: the flag is process-global. */
export function resetChatHeaderSurfaceForTests(): void {
  settingsSurface = false
  listeners.clear()
}

export function ChatHeaderSurfaceProvider({
  suppressed,
  children,
}: {
  suppressed: boolean
  children: ReactNode
}): ReactNode {
  return createElement(ChatHeaderSuppressedContext.Provider, { value: suppressed }, children)
}

export function useChatHeaderSuppressed(): boolean {
  return useContext(ChatHeaderSuppressedContext)
}
