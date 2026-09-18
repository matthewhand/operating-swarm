/**
 * REQ-98: Per-agent browser Notification popups.
 *
 * Opt-in IDs cache in localStorage (`swarm_notify_agents`) — same persistence
 * family as hide/pin/unread. Default is Off. Not written to the server
 * preferences bag.
 *
 * Visibility rule: notify when the page/tab is hidden OR a different rail
 * row is selected. Never on every streaming token.
 */

import { truncateSnippet } from './chatTime'
import { loadAgentChatSessions } from './agentChatSessions'

export const NOTIFY_AGENTS_STORAGE_KEY = 'swarm_notify_agents'
export const NOTIFY_CHANGED_EVENT = 'swarm:notify-changed'
export const FOCUS_AGENT_EVENT = 'swarm:focus-agent'
export const NOTIFY_DEDUPE_MS = 1500
export const NOTIFY_SNIPPET_MAX = 100

const SECRET_LINE =
  /(api[_-]?key|secret|token|password|bearer)\s*[:=]\s*\S+/gi
const SECRET_TOKEN = /\b(sk-[A-Za-z0-9_-]{10,}|gh[ps]_[A-Za-z0-9]{20,})\b/g

let lastNotifyAt = new Map<string, number>()

export function resetNotifyDedupe(): void {
  lastNotifyAt = new Map()
}

export function parseNotifyAgentIds(raw: string | null): string[] {
  if (!raw) return []
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((id): id is string => typeof id === 'string' && id.length > 0)
  } catch {
    return []
  }
}

export function loadNotifyAgentIds(): string[] {
  try {
    return parseNotifyAgentIds(localStorage.getItem(NOTIFY_AGENTS_STORAGE_KEY))
  } catch {
    return []
  }
}

export function saveNotifyAgentIds(ids: string[]): string[] {
  const unique = Array.from(new Set(ids.filter((id) => typeof id === 'string' && id.length > 0)))
  try {
    localStorage.setItem(NOTIFY_AGENTS_STORAGE_KEY, JSON.stringify(unique))
  } catch {
    /* persistence is best-effort */
  }
  try {
    window.dispatchEvent(new CustomEvent(NOTIFY_CHANGED_EVENT, { detail: { notifyIds: unique } }))
  } catch {
    /* non-browser */
  }
  return unique
}

export function isAgentNotifyEnabled(id: string, current?: string[]): boolean {
  if (!id) return false
  const list = current ?? loadNotifyAgentIds()
  return list.includes(id)
}

export function enableAgentNotify(id: string, current?: string[]): string[] {
  if (!id) return current ?? loadNotifyAgentIds()
  const list = current ?? loadNotifyAgentIds()
  if (list.includes(id)) return list
  return saveNotifyAgentIds([...list, id])
}

export function disableAgentNotify(id: string, current?: string[]): string[] {
  if (!id) return current ?? loadNotifyAgentIds()
  const list = current ?? loadNotifyAgentIds()
  if (!list.includes(id)) return list
  return saveNotifyAgentIds(list.filter((item) => item !== id))
}

/**
 * #546: the outcome of asking for notification permission, in the four states
 * that need four different answers.
 *
 * The UI forked on `permission !== 'granted'` and rendered one sentence —
 * "notifications are blocked, enable them in the browser site settings" — which
 * is only true for `denied`. `default` means the prompt **never happened**, and
 * `unsupported` means there is no Notification API in this context at all, so
 * site settings cannot help. Sending the user to the wrong fix is the same
 * dead-end-prose class as #494 and #541.
 */
export type NotifyEnableOutcome = 'granted' | 'denied' | 'never-asked' | 'unsupported'

export function notifyEnableOutcome(
  permission: NotificationPermission | 'unsupported',
): NotifyEnableOutcome {
  if (permission === 'granted') return 'granted'
  if (permission === 'denied') return 'denied'
  if (permission === 'unsupported') return 'unsupported'
  return 'never-asked'
}

/**
 * #546: the honest answer per non-granted state. `unsupported` names the real
 * fix (a secure context) rather than pointing at a setting that cannot exist.
 */
export const NOTIFY_HINT_COPY: Record<
  Exclude<NotifyEnableOutcome, 'granted'>,
  string
> = {
  denied:
    'Notifications are blocked. Enable them in the browser site settings for this page.',
  'never-asked':
    'The browser never asked for permission — the prompt didn’t appear. Try again.',
  unsupported:
    'Notifications can’t work here: browsers only expose the Notification API in a secure context (HTTPS or localhost). This page is on a plain-HTTP address, so no site setting can enable it.',
}

/**
 * #546: whether the Notification API exists in this context at all, so the UI
 * can say why rather than reporting a permission problem.
 */
export function notificationContextSupported(): boolean {
  try {
    return typeof Notification !== 'undefined'
  } catch {
    return false
  }
}

export function notificationPermission(): NotificationPermission | 'unsupported' {
  try {
    if (typeof Notification === 'undefined') return 'unsupported'
    return Notification.permission
  } catch {
    return 'unsupported'
  }
}

export interface NotifyPermissionRequest {
  permission: NotificationPermission | 'unsupported'
  /**
   * #546: the request itself threw. Previously the catch returned the current
   * permission, which made a failed prompt **indistinguishable from a denial** —
   * whatever actually went wrong was discarded.
   */
  requestFailed: boolean
}

export async function requestNotificationPermissionDetailed(): Promise<NotifyPermissionRequest> {
  try {
    if (typeof Notification === 'undefined') {
      return { permission: 'unsupported', requestFailed: false }
    }
    if (Notification.permission !== 'default') {
      return { permission: Notification.permission, requestFailed: false }
    }
    const permission = await Notification.requestPermission()
    return { permission, requestFailed: false }
  } catch {
    return { permission: notificationPermission(), requestFailed: true }
  }
}

/** Kept for existing callers: the permission alone. */
export async function requestNotificationPermission(): Promise<
  NotificationPermission | 'unsupported'
> {
  return (await requestNotificationPermissionDetailed()).permission
}

/** Persist On, then request permission once (browser will not re-prompt if denied). */
export async function enableAgentNotifications(id: string): Promise<{
  ids: string[]
  permission: NotificationPermission | 'unsupported'
  outcome: NotifyEnableOutcome
  requestFailed: boolean
}> {
  const { permission, requestFailed } = await requestNotificationPermissionDetailed()
  return { ids: enableAgentNotify(id), permission, outcome: notifyEnableOutcome(permission), requestFailed }
}

export function redactNotificationSecrets(text: string): string {
  return String(text || '')
    .replace(SECRET_LINE, '$1: …')
    .replace(SECRET_TOKEN, '…')
}

export function snippetForNotification(text: string, maxChars = NOTIFY_SNIPPET_MAX): string {
  return truncateSnippet(redactNotificationSecrets(text), maxChars)
}

export function snippetFromAgentSession(agentId: string): string {
  if (!agentId) return ''
  try {
    const session = loadAgentChatSessions()[agentId]
    const last = [...(session?.messages ?? [])]
      .reverse()
      .find((row) => row.role === 'assistant' && row.text.trim())
    return last ? snippetForNotification(last.text) : ''
  } catch {
    return ''
  }
}

export function chatHrefForRowId(id: string): string {
  if (id.startsWith('team:')) {
    return `/chat?team=${encodeURIComponent(id.slice('team:'.length))}`
  }
  if (id.startsWith('remote:')) {
    return `/chat?remote=${encodeURIComponent(id.slice('remote:'.length))}`
  }
  return `/chat?blueprint=${encodeURIComponent(id)}`
}

export function focusAgentChat(agentId: string): void {
  if (!agentId) return
  try {
    window.focus()
  } catch {
    /* popup / unfocused */
  }
  try {
    window.dispatchEvent(new CustomEvent(FOCUS_AGENT_EVENT, { detail: { agentId } }))
  } catch {
    /* non-browser */
  }
}

export function shouldNotifyAgent(args: {
  agentId: string
  selectedAgentId?: string | null
  tabHidden?: boolean
  permission?: NotificationPermission | 'unsupported'
  enabled?: boolean
}): boolean {
  if (!args.agentId) return false
  const enabled = args.enabled ?? isAgentNotifyEnabled(args.agentId)
  if (!enabled) return false
  const permission = args.permission ?? notificationPermission()
  if (permission !== 'granted') return false
  const tabHidden =
    args.tabHidden ?? (typeof document !== 'undefined' ? document.hidden : false)
  const selected = args.selectedAgentId ?? ''
  const otherSelected = selected !== args.agentId
  return tabHidden || otherSelected
}

export function showAgentNotification(opts: {
  agentId: string
  agentName?: string
  snippet?: string
  failed?: boolean
}): Notification | null {
  try {
    if (typeof Notification === 'undefined') return null
    if (Notification.permission !== 'granted') return null
    const title = (opts.agentName || opts.agentId || 'Agent').trim() || 'Agent'
    const snippet = snippetForNotification(opts.snippet || '')
    const body = opts.failed
      ? snippet
        ? `Failed: ${snippet}`
        : 'Run failed'
      : snippet || 'Reply ready'
    const notification = new Notification(title, {
      body,
      tag: `swarm-agent-${opts.agentId}`,
    })
    notification.onclick = () => {
      try {
        notification.close()
      } catch {
        /* ignore */
      }
      focusAgentChat(opts.agentId)
    }
    return notification
  } catch {
    return null
  }
}

export function maybeNotifyAgentTurn(opts: {
  agentId: string
  agentName?: string
  snippet?: string
  failed?: boolean
  selectedAgentId?: string | null
  tabHidden?: boolean
}): Notification | null {
  if (
    !shouldNotifyAgent({
      agentId: opts.agentId,
      selectedAgentId: opts.selectedAgentId,
      tabHidden: opts.tabHidden,
    })
  ) {
    return null
  }
  const now = Date.now()
  const last = lastNotifyAt.get(opts.agentId) ?? 0
  if (now - last < NOTIFY_DEDUPE_MS) return null
  lastNotifyAt.set(opts.agentId, now)
  const snippet = opts.snippet ? snippetForNotification(opts.snippet) : snippetFromAgentSession(opts.agentId)
  return showAgentNotification({
    agentId: opts.agentId,
    agentName: opts.agentName,
    snippet,
    failed: opts.failed,
  })
}
