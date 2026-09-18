import type { Agent, AvatarEyes, AvatarTheme, ChatMessage, DelegationEvent } from '../types/agent'
import { AVATAR_EYES, AVATAR_THEMES } from '../types/agent'
import { agentTypeOf } from './agent-types'
import { isSupportAgent } from './starter-agents'
import {
  avatarsForFamily,
  expandAvatarFamilies,
  loadEnabledAvatarThemes,
  uniqueAvatarFamilies,
  type AvatarThemeChoice,
} from './avatarTheme'

export type SearchScope = 'all' | 'bots' | 'messages' | 'delegations'

export interface SearchHit {
  kind: 'bot' | 'message' | 'delegation'
  id: string
  title: string
  subtitle: string
  agentId?: string
}

function matchesQuery(haystack: string, q: string): boolean {
  if (!q) return true
  return haystack.toLowerCase().includes(q)
}

/** Default sidebar sections by run type. Ignores `agent.group` (custom drag target only). */
export function groupAgents(agents: Agent[]): Record<string, Agent[]> {
  const groups: Record<string, Agent[]> = {
    api: [],
    cli: [],
    remote: [],
  }

  for (const agent of agents) {
    if (isSupportAgent(agent)) continue
    groups[agentTypeOf(agent)].push(agent)
  }

  return groups
}

export function formatTimestamp(date: Date | number): string {
  const d = typeof date === 'number' ? new Date(date * 1000) : date
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function getInitials(name: string): string {
  if (!name) return '?'
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[1][0]).toUpperCase()
}

export function getReadableTextColor(hexColor: string): string {
  if (!hexColor || !hexColor.startsWith('#')) return '#ffffff'
  const hex = hexColor.replace('#', '')
  const r = parseInt(hex.substring(0, 2), 16) || 0
  const g = parseInt(hex.substring(2, 4), 16) || 0
  const b = parseInt(hex.substring(4, 6), 16) || 0
  // YIQ luminance formula
  const yiq = (r * 299 + g * 587 + b * 114) / 1000
  return yiq >= 128 ? '#1e1e2e' : '#ffffff'
}

export function buildSearchHits(opts: {
  agents: Agent[]
  messages?: ChatMessage[]
  delegations?: DelegationEvent[]
  query: string
  scope: SearchScope
  recentAgentIds?: string[]
}): SearchHit[] {
  const q = opts.query.trim().toLowerCase()
  const empty = !q
  const includeBots = opts.scope === 'all' || opts.scope === 'bots'
  const includeMessages = opts.scope === 'all' || opts.scope === 'messages'
  const includeDelegations = opts.scope === 'all' || opts.scope === 'delegations'
  const hits: SearchHit[] = []

  if (includeBots) {
    const recent = new Set(opts.recentAgentIds || [])
    const ranked = [...opts.agents].sort((a, b) => {
      const ar = recent.has(a.agent_id) ? 0 : 1
      const br = recent.has(b.agent_id) ? 0 : 1
      return ar - br
    })
    for (const agent of ranked) {
      const name = agent.customName || agent.name
      const blob = [name, agent.customPurpose || agent.specialty, agent.description, agent.group, agent.kind]
        .filter(Boolean)
        .join(' ')
      if (!matchesQuery(blob, q)) continue
      hits.push({
        kind: 'bot',
        id: `bot:${agent.agent_id}`,
        title: name,
        subtitle: agent.customPurpose || agent.specialty || agent.group || 'Agent',
        agentId: agent.agent_id,
      })
    }
  }

  if (includeMessages) {
    const msgs = [...(opts.messages || [])].reverse()
    for (const msg of msgs) {
      const blob = [msg.text, msg.agent, msg.agent_id, msg.role].filter(Boolean).join(' ')
      if (!matchesQuery(blob, q)) continue
      hits.push({
        kind: 'message',
        id: `msg:${msg.key}`,
        title: msg.text.slice(0, 80) || '(empty)',
        subtitle: msg.role === 'user' ? 'You' : msg.agent || 'Assistant',
        agentId: msg.agent_id,
      })
    }
  }

  if (includeDelegations) {
    for (const del of opts.delegations || []) {
      const blob = [del.query, del.response, del.from_agent_name, del.to_agent_name].join(' ')
      if (!matchesQuery(blob, q)) continue
      hits.push({
        kind: 'delegation',
        id: `del:${del.id}`,
        title: del.query.slice(0, 80) || 'Delegation',
        subtitle: `${del.from_agent_name} → ${del.to_agent_name}`,
        agentId: del.to_agent,
      })
    }
  }

  if (empty) return hits.slice(0, 40)
  return hits
}

function shuffleInPlace<T>(items: T[], random: () => number): T[] {
  for (let i = items.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1))
    const tmp = items[i]
    items[i] = items[j]
    items[j] = tmp
  }
  return items
}

/**
 * Every body×eyes pair. Pass `themes` (the installed set) to build the deck from
 * those packs only — assigning a look from a pack the operator never installed
 * just stores a value `resolveAvatarTheme` then has to fall back from (#128).
 */
export function allAvatarLooks(
  themes?: readonly AvatarTheme[],
): { theme: AvatarTheme; eyes: AvatarEyes }[] {
  // Installed families expand to their avatars (blobs → blobs; robots → ten
  // bodies), so the deck is the installed set × eye styles.
  const installed = themes?.length
    ? expandAvatarFamilies(uniqueAvatarFamilies([...themes]))
    : []
  const pool = installed.length ? installed : AVATAR_THEMES.map((pack) => pack.id)
  const out: { theme: AvatarTheme; eyes: AvatarEyes }[] = []
  for (const theme of pool) {
    for (const eye of AVATAR_EYES) {
      out.push({ theme, eyes: eye.id })
    }
  }
  return out
}

/**
 * #563: stamp every agent with the persisted default-theme choice. `mixed`
 * deals unique looks from the enabled set (the pre-#563 "Apply" behaviour,
 * REQ-842); a specific family stamps that family's first theme on every
 * agent, preserving each agent's explicit per-agent pick (custom uploads win).
 * Mutates nothing directly — callers commit the returned maps to the store.
 */
export function applyAvatarThemeChoice(
  agentIds: string[],
  choice: AvatarThemeChoice,
  enabled: AvatarTheme[] = loadEnabledAvatarThemes(),
  random: () => number = Math.random,
): { themes: Record<string, AvatarTheme>; eyes: Record<string, AvatarEyes> } {
  if (choice === 'mixed') {
    return assignUniqueLooks(agentIds, {}, {}, { reassignAll: true, themes: enabled, random })
  }
  // Intersect the chosen family's themes with the installed set so a stale
  // choice (family uninstalled after selection) cannot stamp a missing look.
  // If the family is gone entirely, fall back to what IS installed.
  const installedFamily = new Set(
    expandAvatarFamilies([choice]).filter((t) => enabled.includes(t)),
  )
  const pool = installedFamily.size
    ? [...installedFamily]
    : enabled.length
      ? [enabled[0]]
      : avatarsForFamily(choice).map((a) => a.id)
  const theme = pool[0]
  if (!theme) return { themes: {}, eyes: {} }
  const themes: Record<string, AvatarTheme> = {}
  const eyes: Record<string, AvatarEyes> = {}
  const deck = shuffleInPlace(
    pool.flatMap((t) => allAvatarLooks([t]).map((look) => ({ theme: t, eyes: look.eyes }))),
    random,
  )
  agentIds.forEach((id, i) => {
    const pick = deck[i % deck.length]
    if (!pick) return
    themes[id] = pick.theme
    eyes[id] = pick.eyes
  })
  return { themes, eyes }
}

/** Unique body+eyes pairs for each agent. Repeats only after the 60-combo deck is used. */
export function assignUniqueLooks(
  agentIds: string[],
  existingThemes: Record<string, AvatarTheme> = {},
  existingEyes: Record<string, AvatarEyes> = {},
  opts?: { reassignAll?: boolean; random?: () => number; themes?: readonly AvatarTheme[] },
): { themes: Record<string, AvatarTheme>; eyes: Record<string, AvatarEyes> } {
  const random = opts?.random ?? Math.random
  const pool = allAvatarLooks(opts?.themes)
  const themes: Record<string, AvatarTheme> = opts?.reassignAll ? {} : { ...existingThemes }
  const eyes: Record<string, AvatarEyes> = opts?.reassignAll ? {} : { ...existingEyes }
  const taken = new Set<string>()
  for (const id of agentIds) {
    if (themes[id] && eyes[id]) taken.add(`${themes[id]}:${eyes[id]}`)
  }
  const deck = shuffleInPlace(
    pool.filter((look) => !taken.has(`${look.theme}:${look.eyes}`)),
    random,
  )
  let i = 0
  const overflow = shuffleInPlace(pool, random)
  for (const id of agentIds) {
    if (themes[id] && eyes[id]) continue
    const pick = deck[i] ?? overflow[i % overflow.length]
    i += 1
    if (!pick) continue
    themes[id] = pick.theme
    eyes[id] = pick.eyes
  }
  return { themes, eyes }
}
