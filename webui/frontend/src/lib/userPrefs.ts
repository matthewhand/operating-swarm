/**
 * Django-backed UI preferences (REQ-144 / #540, REQ-168 / #592).
 *
 * Favourites, Hidden Bots, hostname override, and per-agent dropdown
 * choices (CLI / model / remote / blueprint) load from GET
 * /v1/preferences/ and persist on change via PATCH. localStorage stays a
 * cache: if the server bag is empty and this browser already has values,
 * import once, then the server wins.
 *
 * Unexpected / offline responses keep the local cache (do not treat a
 * blueprint list mock as "empty server").
 */

import { apiGet, apiPatch, ensureCsrfCookie } from './api'
import {
  hasHiddenAgentsStorage,
  loadHiddenAgentIds,
  loadOrSeedHiddenAgentIds,
  saveHiddenAgentIds,
} from './hiddenAgents'
import { defaultHostname, HOSTNAME_STORAGE_KEY, saveHostname } from './hostname'
import {
  hasPinnedAgentsStorage,
  loadOrSeedPinnedAgents,
  loadPinnedAgents,
  savePinnedAgents,
  type PinnedAgent,
} from './pinnedAgents'
import { saveAgentRemoteBinding } from './agentRemote'
import {
  applyLocalAgentDropdowns,
  loadAllLocalAgentDropdowns,
  parseAgentDropdowns,
  saveLocalAgentDropdown,
  type AgentDropdownChoice,
  type AgentDropdowns,
} from './agentSettings'
import {
  hasHostnameOverrideStorage,
  loadHostnameOverride,
  saveHostnameOverride,
} from './settingsPrefs'
import {
  DEFAULT_CONTEXT_STRATEGY,
  parseContextStrategy,
  parseCullFractionPct,
  parseCullTriggerPct,
  type ContextStrategy,
} from './contextCull'

export type { ContextStrategy } from './contextCull'

export type { AgentDropdownChoice, AgentDropdowns }

export const USER_PREFS_PATH = '/v1/preferences/'

export const DEFAULT_AUTO_COMPRESS_PCT = 80
export const MIN_AUTO_COMPRESS_PCT = 1
export const MAX_AUTO_COMPRESS_PCT = 99

export interface UserPrefs {
  object: 'user_preferences'
  principal: string
  guest: boolean
  empty: boolean
  favourites: PinnedAgent[]
  hidden_agents: string[]
  hostname_override: string
  context_auto_compress_pct: number
  context_strategy: ContextStrategy
  context_cull_trigger_pct: number
  context_cull_fraction_pct: number
  values?: Record<string, unknown>
  agent_dropdowns: AgentDropdowns
}

export function parseAutoCompressPct(raw: unknown): number {
  const value = typeof raw === 'number' ? raw : typeof raw === 'string' ? Number(raw) : NaN
  if (!Number.isFinite(value)) return DEFAULT_AUTO_COMPRESS_PCT
  return Math.min(MAX_AUTO_COMPRESS_PCT, Math.max(MIN_AUTO_COMPRESS_PCT, Math.round(value)))
}

export type RailPrefs = {
  pins: PinnedAgent[]
  hidden: string[]
  hostnameOverride: string
  source: 'server' | 'import' | 'local'
}

function normalizePin(value: unknown): PinnedAgent | null {
  if (typeof value === 'string' && value.length > 0) {
    return { id: value, name: value }
  }
  if (!value || typeof value !== 'object') return null
  const rec = value as { id?: unknown; name?: unknown }
  if (typeof rec.id !== 'string' || rec.id.length === 0) return null
  return {
    id: rec.id,
    name: typeof rec.name === 'string' && rec.name.length > 0 ? rec.name : rec.id,
  }
}

export function parseUserPrefs(raw: unknown): UserPrefs | null {
  if (!raw || typeof raw !== 'object') return null
  const rec = raw as Record<string, unknown>
  if (rec.object !== 'user_preferences') return null
  const pins: PinnedAgent[] = []
  const seen = new Set<string>()
  if (Array.isArray(rec.favourites)) {
    for (const item of rec.favourites) {
      const pin = normalizePin(item)
      if (!pin || seen.has(pin.id)) continue
      seen.add(pin.id)
      pins.push(pin)
    }
  }
  const hidden = Array.isArray(rec.hidden_agents)
    ? rec.hidden_agents.filter((id): id is string => typeof id === 'string' && id.length > 0)
    : []
  const hostname =
    typeof rec.hostname_override === 'string' ? rec.hostname_override.trim() : ''
  const values =
    rec.values && typeof rec.values === 'object' && !Array.isArray(rec.values)
      ? (rec.values as Record<string, unknown>)
      : {}
  const fromTop = parseAgentDropdowns(rec.agent_dropdowns)
  const fromValues = parseAgentDropdowns(values.agent_dropdowns)
  const pctRaw =
    rec.context_auto_compress_pct !== undefined
      ? rec.context_auto_compress_pct
      : values.context_auto_compress_pct
  const strategyRaw =
    rec.context_strategy !== undefined ? rec.context_strategy : values.context_strategy
  const cullTriggerRaw =
    rec.context_cull_trigger_pct !== undefined
      ? rec.context_cull_trigger_pct
      : values.context_cull_trigger_pct
  const cullFractionRaw =
    rec.context_cull_fraction_pct !== undefined
      ? rec.context_cull_fraction_pct
      : values.context_cull_fraction_pct
  return {
    object: 'user_preferences',
    principal: typeof rec.principal === 'string' ? rec.principal : '',
    guest: rec.guest === true,
    empty: rec.empty === true,
    favourites: pins,
    hidden_agents: Array.from(new Set(hidden)),
    hostname_override: hostname,
    context_auto_compress_pct: parseAutoCompressPct(pctRaw),
    context_strategy: parseContextStrategy(strategyRaw ?? DEFAULT_CONTEXT_STRATEGY),
    context_cull_trigger_pct: parseCullTriggerPct(cullTriggerRaw),
    context_cull_fraction_pct: parseCullFractionPct(cullFractionRaw),
    values,
    agent_dropdowns:
      Object.keys(fromTop).length > 0 ? fromTop : fromValues,
  }
}

export function prefsAgentDropdowns(prefs: UserPrefs | null | undefined): AgentDropdowns {
  if (!prefs) return {}
  if (Object.keys(prefs.agent_dropdowns).length > 0) return prefs.agent_dropdowns
  return parseAgentDropdowns(prefs.values?.agent_dropdowns)
}

export function applyHostnameOverride(value: string): string {
  const trimmed = value.trim()
  saveHostnameOverride(trimmed)
  saveHostname(trimmed || defaultHostname())
  return trimmed
}

export function localHostnameOverride(): string {
  if (hasHostnameOverrideStorage()) return loadHostnameOverride()
  try {
    const rail = localStorage.getItem(HOSTNAME_STORAGE_KEY)
    if (rail && rail.trim().length > 0 && rail.trim() !== defaultHostname()) {
      return rail.trim()
    }
  } catch {
    /* ignore */
  }
  return loadHostnameOverride()
}

export function applyPrefsToLocal(prefs: {
  favourites: PinnedAgent[]
  hidden_agents: string[]
  hostname_override?: string
}): void {
  savePinnedAgents(prefs.favourites)
  saveHiddenAgentIds(prefs.hidden_agents)
  if (typeof prefs.hostname_override === 'string') {
    applyHostnameOverride(prefs.hostname_override)
  }
}

export async function fetchUserPrefs(): Promise<UserPrefs | null> {
  try {
    const data = await apiGet<unknown>(USER_PREFS_PATH)
    return parseUserPrefs(data)
  } catch {
    return null
  }
}

export async function saveUserPrefs(patch: {
  favourites?: PinnedAgent[]
  hidden_agents?: string[]
  hostname_override?: string
  context_auto_compress_pct?: number
  context_strategy?: ContextStrategy
  context_cull_trigger_pct?: number
  context_cull_fraction_pct?: number
  values?: Record<string, unknown>
  agent_dropdowns?: AgentDropdowns
}): Promise<UserPrefs | null> {
  if (
    patch.favourites === undefined &&
    patch.hidden_agents === undefined &&
    patch.hostname_override === undefined &&
    patch.context_auto_compress_pct === undefined &&
    patch.context_strategy === undefined &&
    patch.context_cull_trigger_pct === undefined &&
    patch.context_cull_fraction_pct === undefined &&
    patch.values === undefined &&
    patch.agent_dropdowns === undefined
  ) {
    return null
  }
  const body: Record<string, unknown> = {}
  if (patch.favourites !== undefined) body.favourites = patch.favourites
  if (patch.hidden_agents !== undefined) body.hidden_agents = patch.hidden_agents
  if (patch.hostname_override !== undefined) body.hostname_override = patch.hostname_override
  if (patch.context_auto_compress_pct !== undefined) {
    body.context_auto_compress_pct = parseAutoCompressPct(patch.context_auto_compress_pct)
  }
  if (patch.context_strategy !== undefined) {
    body.context_strategy = parseContextStrategy(patch.context_strategy)
  }
  if (patch.context_cull_trigger_pct !== undefined) {
    body.context_cull_trigger_pct = parseCullTriggerPct(patch.context_cull_trigger_pct)
  }
  if (patch.context_cull_fraction_pct !== undefined) {
    body.context_cull_fraction_pct = parseCullFractionPct(patch.context_cull_fraction_pct)
  }
  const values = { ...(patch.values || {}) }
  if (patch.agent_dropdowns !== undefined) values.agent_dropdowns = patch.agent_dropdowns
  if (Object.keys(values).length > 0) body.values = values
  try {
    await ensureCsrfCookie()
    const data = await apiPatch<unknown>(USER_PREFS_PATH, body)
    const parsed = parseUserPrefs(data)
    if (parsed && !parsed.empty) {
      applyPrefsToLocal(parsed)
    }
    return parsed
  } catch {
    return null
  }
}

const DROPDOWN_SAVE_MS = 300
let dropdownSaveTimer: ReturnType<typeof setTimeout> | undefined

export function persistAgentDropdownChoice(
  agentId: string,
  patch: AgentDropdownChoice,
): AgentDropdownChoice {
  const next = saveLocalAgentDropdown(agentId, patch)
  if (dropdownSaveTimer) clearTimeout(dropdownSaveTimer)
  dropdownSaveTimer = setTimeout(() => {
    void saveUserPrefs({ agent_dropdowns: loadAllLocalAgentDropdowns() })
  }, DROPDOWN_SAVE_MS)
  return next
}

export function localRailSnapshot(
  catalog: Array<{ id: string; name?: string | null }> = [],
): RailPrefs {
  const pins = hasPinnedAgentsStorage() ? loadPinnedAgents() : loadOrSeedPinnedAgents()
  const hidden = hasHiddenAgentsStorage()
    ? loadHiddenAgentIds()
    : loadOrSeedHiddenAgentIds(catalog)
  return { pins, hidden, hostnameOverride: localHostnameOverride(), source: 'local' }
}

/**
 * Session start: server bag wins when present; otherwise one-time import
 * of the local cache (including first-load Support / gate+skeptic seeds).
 */
export async function hydrateRailPrefs(
  catalog: Array<{ id: string; name?: string | null }> = [],
): Promise<RailPrefs> {
  const server = await fetchUserPrefs()
  if (server && !server.empty) {
    applyPrefsToLocal(server)
    const dropdowns = prefsAgentDropdowns(server)
    if (Object.keys(dropdowns).length > 0) {
      applyLocalAgentDropdowns(dropdowns)
      for (const [agentId, choice] of Object.entries(dropdowns)) {
        if (choice.remote) {
          saveAgentRemoteBinding(agentId, { id: choice.remote, kind: choice.remote })
        }
      }
    }
    return {
      pins: server.favourites,
      hidden: server.hidden_agents,
      hostnameOverride: server.hostname_override,
      source: 'server',
    }
  }
  const local = localRailSnapshot(catalog)
  const localDropdowns = loadAllLocalAgentDropdowns()
  if (server?.empty) {
    await saveUserPrefs({
      favourites: local.pins,
      hidden_agents: local.hidden,
      hostname_override: local.hostnameOverride,
      agent_dropdowns: localDropdowns,
    })
    return { ...local, source: 'import' }
  }
  return local
}
