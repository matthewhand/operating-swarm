/**
 * #527 — per-persona avatar themes for openai-agents blueprint seats.
 *
 * A blueprint that declares multiple personas (REQ-81 static parse) may carry
 * one avatar theme per persona. Assignments live in localStorage under
 * `swarm_persona_avatar_themes` keyed `agentId → persona → theme`, mirroring
 * the `avatarThemeByAgent` per-agent pattern.
 *
 * Chat-row attribution (`personaForAgentMessage`) is deliberately honest:
 * the explicit `persona` field wins; otherwise `sender`/`agent` must exactly
 * match a *declared* persona name (case-insensitive); everything else belongs
 * to the agent itself, so nothing is ever invented.
 */
import type { AvatarTheme } from '../types/agent'
import type { ChatMessage } from '../types/agent'

export const PERSONA_AVATAR_THEMES_KEY = 'swarm_persona_avatar_themes'

/** agentId → persona name → avatar theme. */
export type PersonaAvatarThemeMap = Record<string, AvatarTheme>

export type PersonaAvatarThemeStore = Record<string, PersonaAvatarThemeMap>

export interface DeclaredPersona {
  name: string
}

function readStore(): PersonaAvatarThemeStore {
  try {
    const raw = localStorage.getItem(PERSONA_AVATAR_THEMES_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return parsed as PersonaAvatarThemeStore
  } catch {
    return {}
  }
}

function writeStore(store: PersonaAvatarThemeStore): void {
  try {
    localStorage.setItem(PERSONA_AVATAR_THEMES_KEY, JSON.stringify(store))
  } catch {
    /* persistence is best-effort */
  }
}

export function personaAvatarThemes(agentId: string | null | undefined): PersonaAvatarThemeMap {
  const key = String(agentId || '').trim()
  if (!key) return {}
  return readStore()[key] ?? {}
}

export function setPersonaAvatarTheme(
  agentId: string | null | undefined,
  persona: string,
  theme: AvatarTheme,
): void {
  const key = String(agentId || '').trim()
  if (!key || !persona) return
  const store = readStore()
  const next: PersonaAvatarThemeMap = { ...(store[key] ?? {}) }
  next[persona] = theme
  writeStore({ ...store, [key]: next })
}

export function clearPersonaAvatarTheme(
  agentId: string | null | undefined,
  persona: string,
): void {
  const key = String(agentId || '').trim()
  if (!key || !persona) return
  const store = readStore()
  const current = store[key]
  if (!current || !(persona in current)) return
  const next = { ...current }
  delete next[persona]
  writeStore({ ...store, [key]: next })
}

/**
 * Which declared persona produced a chat row, or `null` when the row belongs
 * to the agent itself (or the name matches nothing declared).
 */
export function personaForAgentMessage(
  message: Pick<ChatMessage, 'persona' | 'sender' | 'agent'>,
  personas: readonly DeclaredPersona[] | undefined,
): string | null {
  const declared = (personas ?? []).map((row) => row.name).filter(Boolean)
  // Single-persona (or absent) rosters never attribute — there is nothing to
  // switch between.
  if (declared.length < 2) return null
  const explicit = typeof message.persona === 'string' ? message.persona.trim() : ''
  if (explicit) {
    const match = declared.find((name) => name.toLowerCase() === explicit.toLowerCase())
    return match ?? null
  }
  const candidates = [message.sender, message.agent]
  for (const candidate of candidates) {
    const name = typeof candidate === 'string' ? candidate.trim() : ''
    if (!name) continue
    const match = declared.find(
      (declaredName) => declaredName.toLowerCase() === name.toLowerCase(),
    )
    if (match) return match
  }
  return null
}
