/**
 * REQ-161 — quiet restore chrome when an existing session is reopened.
 *
 * Only prepend a status line when hydrate actually found prior turns.
 * Kind-aware wording; never invent restore for an empty thread.
 */

import { classifyAgentKind } from './agentKind'
import { isCliBlueprintId } from './cliAgentContext'

export type RestoreKind = 'cli' | 'api' | 'remote' | 'team'

export const RESTORED_SESSION_TEXT: Record<RestoreKind, string> = {
  cli: 'Resumed CLI session',
  api: 'Restored session',
  remote: 'Reconnected remote',
  team: 'Restored session',
}

/** REQ-105: honest status after the user picks or creates a session. */
export function switchedSessionNotice(title?: string | null): string {
  const label = String(title || '').trim()
  return label ? `Switched to session ${label}` : 'Switched to session'
}

/** #794: stored session id is gone — never silently swap to another transcript. */
export const MISSING_SESSION_TEXT = 'Stored session is gone'

export function missingSessionNotice(sessionId?: string | null): string {
  const id = String(sessionId || '').trim()
  return id ? `Stored session ${id} is gone` : MISSING_SESSION_TEXT
}

export function restoreKindForAgent(agentId: string): RestoreKind {
  const id = (agentId || '').trim().toLowerCase()
  if (id.startsWith('team-') || id.startsWith('team:')) return 'team'
  if (
    id.startsWith('remote:') ||
    id.startsWith('remote-') ||
    id.startsWith('placeholder:remote:')
  ) {
    return 'remote'
  }
  if (id === 'api_agent') return 'api'
  if (isCliBlueprintId(id) || id === 'cli_agent' || /_agent$/.test(id)) return 'cli'
  // Generic blueprint seats are API-backed; the kind classifier's 'blueprint'
  // value has no distinct restore wording, so it shares the API banner.
  const kind = classifyAgentKind(id)
  return kind === 'blueprint' ? 'api' : kind
}

export function isRestoreStatusText(text: string | null | undefined): boolean {
  const t = String(text || '').trim().toLowerCase()
  if (!t) return false
  return (
    t.startsWith('restored session') ||
    t.startsWith('resumed ') ||
    t.startsWith('reconnected remote') ||
    t.startsWith('continued chat') ||
    t.startsWith('switched to session') ||
    t.startsWith('stored session')
  )
}

export function hasRestorableTurns(messages: Array<{ role: string }>): boolean {
  return messages.some((row) => row.role === 'user' || row.role === 'assistant')
}

export function withRestoredSession<T extends { role: string; content: string }>(
  messages: T[],
  kind: RestoreKind,
): T[] {
  if (!hasRestorableTurns(messages)) return messages
  if (messages.some((row) => row.role === 'status' && isRestoreStatusText(row.content))) {
    return messages
  }
  const line = RESTORED_SESSION_TEXT[kind]
  return [{ role: 'status', content: line } as T, ...messages]
}

/** Banner text for hydrate, or null when nothing was actually restored. */
export function restoredSessionNotice(
  messages: Array<{ role: string; content?: string }>,
  kind: RestoreKind,
): string | null {
  if (!hasRestorableTurns(messages)) return null
  if (messages.some((row) => row.role === 'status' && isRestoreStatusText(row.content))) {
    return null
  }
  return RESTORED_SESSION_TEXT[kind]
}
