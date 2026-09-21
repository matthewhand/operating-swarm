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

import { apiGet, apiPatch, ensureCsrfCookie, isThrottleError } from './api'
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
  hasRailSectionsStorage,
  loadRailSections,
  parseRailSectionsValue,
  railSectionsHasContent,
  saveRailSections,
  type RailSectionsState,
} from './railSections'
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
import {
  initialNavbarThemeMode,
  initialTheme,
  persistNavbarThemeMode,
  persistTheme,
  dispatchSetNavbarThemeMode,
  dispatchSetTheme,
  type NavbarThemeToggleMode,
  type Theme,
} from './theme'
import {
  loadBubbleTheme,
  saveBubbleTheme,
  type BubbleTheme,
} from './bubbleTheme'

export type { ContextStrategy } from './contextCull'

export type { AgentDropdownChoice, AgentDropdowns }

export const USER_PREFS_PATH = '/v1/preferences/'

export const USER_PREFS_CHANGED_EVENT = 'swarm:user-prefs-changed'

export function dispatchUserPrefsChanged(prefs: UserPrefs): void {
  try {
    window.dispatchEvent(
      new CustomEvent<UserPrefs>(USER_PREFS_CHANGED_EVENT, { detail: prefs }),
    )
  } catch {
    /* ignore in environments without window */
  }
}

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
  theme?: Theme
  theme_navbar_mode?: NavbarThemeToggleMode
  bubble_theme?: string
  /** #786: sidepane sections + membership, server-persisted. */
  rail_sections?: RailSectionsState
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
  /** #786: sidepane layout, when the hydrate source carried one. */
  sections?: RailSectionsState
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
  const themeRaw = rec.theme ?? values.theme
  const theme: Theme | undefined =
    themeRaw === 'light' || themeRaw === 'dark' || themeRaw === 'system'
      ? themeRaw
      : undefined
  const navbarModeRaw = rec.theme_navbar_mode ?? values.theme_navbar_mode
  const themeNavbarMode: NavbarThemeToggleMode | undefined =
    navbarModeRaw === 'if_not_system' || navbarModeRaw === 'always' || navbarModeRaw === 'never'
      ? navbarModeRaw
      : undefined
  const bubbleThemeRaw = rec.bubble_theme ?? values.bubble_theme
  const bubbleTheme = typeof bubbleThemeRaw === 'string' ? bubbleThemeRaw.trim() : undefined
  // #786: server-persisted sidepane layout (top-level canonical key, with a
  // values-bag fallback for rows written before the registry entry).
  const railSectionsRaw = rec.rail_sections ?? values.rail_sections
  const railSections =
    railSectionsRaw === undefined ? undefined : parseRailSectionsValue(railSectionsRaw)
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
    theme,
    theme_navbar_mode: themeNavbarMode,
    bubble_theme: bubbleTheme,
    rail_sections: railSections,
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
  theme?: Theme
  theme_navbar_mode?: NavbarThemeToggleMode
  bubble_theme?: string
  rail_sections?: RailSectionsState
}): void {
  savePinnedAgents(prefs.favourites)
  saveHiddenAgentIds(prefs.hidden_agents)
  // #786: adopt only a layout that actually defines something — the backend
  // canonicalizes every row to include an empty rail_sections default, so
  // emptiness cannot be told apart from "written before #786". An empty
  // server bag leaves the local cache alone; the debounced sync pushes the
  // local layout up instead.
  if (railSectionsHasContent(prefs.rail_sections) && prefs.rail_sections) {
    saveRailSections(prefs.rail_sections)
  }
  if (typeof prefs.hostname_override === 'string') {
    applyHostnameOverride(prefs.hostname_override)
  }
  if (prefs.theme) {
    persistTheme(prefs.theme)
    dispatchSetTheme(prefs.theme)
  }
  if (prefs.theme_navbar_mode) {
    persistNavbarThemeMode(prefs.theme_navbar_mode)
    dispatchSetNavbarThemeMode(prefs.theme_navbar_mode)
  }
  if (typeof prefs.bubble_theme === 'string' && prefs.bubble_theme.length > 0) {
    saveBubbleTheme(prefs.bubble_theme as BubbleTheme)
  }
}

// #726: /v1/preferences/ is read by several surfaces on page load (ChatPage
// hydrate, SettingsSheet, RoleAgentTip, DefaultLlmTip). Share one in-flight
// GET and reuse the parsed bag for a short window so mounting four components
// costs one request, not four. Any real PATCH invalidates the cache.
let _prefsGetPromise: Promise<UserPrefs | null> | null = null
let _prefsCache: { at: number; value: UserPrefs | null } | null = null
const PREFS_GET_CACHE_MS = 60_000

export function invalidateUserPrefsCache(): void {
  _prefsGetPromise = null
  _prefsCache = null
}

/** Test isolation only: reset the #726 dedupe state between tests. */
export function __resetUserPrefsCacheForTests(): void {
  invalidateUserPrefsCache()
}

export function fetchUserPrefs(): Promise<UserPrefs | null> {
  if (_prefsGetPromise) return _prefsGetPromise
  if (_prefsCache && Date.now() - _prefsCache.at < PREFS_GET_CACHE_MS) {
    return Promise.resolve(_prefsCache.value)
  }
  const request = (async () => {
    try {
      const data = await apiGet<unknown>(USER_PREFS_PATH)
      return parseUserPrefs(data)
    } catch {
      return null
    }
  })()
  _prefsGetPromise = request
  void request.then((value) => {
    // Cache successes and failures alike: under throttle the local bag is the
    // honest fallback and re-GETting immediately just re-429s.
    _prefsCache = { at: Date.now(), value }
    if (_prefsGetPromise === request) _prefsGetPromise = null
  })
  return request
}
// #738: module-level 429 back-off for PATCH /v1/preferences/.
// When the server throttles us, skip the PATCH for 30s — localStorage already
// holds the latest value, so no data is lost. The next non-skipped call syncs.
let _prefsPatchThrottledUntil = 0
const PREFS_PATCH_BACKOFF_MS = 30_000

export async function saveUserPrefs(patch: {
  favourites?: PinnedAgent[]
  hidden_agents?: string[]
  hostname_override?: string
  context_auto_compress_pct?: number
  context_strategy?: ContextStrategy
  context_cull_trigger_pct?: number
  context_cull_fraction_pct?: number
  theme?: Theme
  theme_navbar_mode?: NavbarThemeToggleMode
  bubble_theme?: string
  rail_sections?: RailSectionsState
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
    patch.theme === undefined &&
    patch.theme_navbar_mode === undefined &&
    patch.bubble_theme === undefined &&
    patch.rail_sections === undefined &&
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
  if (patch.theme !== undefined) body.theme = patch.theme
  if (patch.theme_navbar_mode !== undefined) body.theme_navbar_mode = patch.theme_navbar_mode
  if (patch.bubble_theme !== undefined) body.bubble_theme = patch.bubble_theme
  if (patch.rail_sections !== undefined) body.rail_sections = patch.rail_sections
  const values = { ...(patch.values || {}) }
  if (patch.agent_dropdowns !== undefined) values.agent_dropdowns = patch.agent_dropdowns
  if (Object.keys(values).length > 0) body.values = values

  // #738: skip the PATCH if still within the back-off window
  if (Date.now() < _prefsPatchThrottledUntil) return null

  try {
    await ensureCsrfCookie()
    const data = await apiPatch<unknown>(USER_PREFS_PATH, body)
    invalidateUserPrefsCache()
    const parsed = parseUserPrefs(data)
    if (parsed && !parsed.empty) {
      applyPrefsToLocal(parsed)
    }
    if (parsed) dispatchUserPrefsChanged(parsed)
    return parsed
  } catch (err) {
    // #738: on 429, back off for PREFS_PATCH_BACKOFF_MS before retrying
    if (isThrottleError(err)) {
      _prefsPatchThrottledUntil = Date.now() + PREFS_PATCH_BACKOFF_MS
      invalidateUserPrefsCache()
    }
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
    // #786: the effective layout after hydrate — the server's when it has
    // content, otherwise this browser's untouched local bag.
    const sections = railSectionsHasContent(server.rail_sections)
      ? server.rail_sections
      : hasRailSectionsStorage()
        ? loadRailSections()
        : undefined
    return {
      pins: server.favourites,
      hidden: server.hidden_agents,
      hostnameOverride: server.hostname_override,
      sections,
      source: 'server',
    }
  }
  const local = localRailSnapshot(catalog)
  const localDropdowns = loadAllLocalAgentDropdowns()
  if (server?.empty) {
    // #786: one-time import — this browser's sections bag seeds the server
    // row only when the browser has actually persisted one.
    const localSections = hasRailSectionsStorage() ? loadRailSections() : undefined
    await saveUserPrefs({
      favourites: local.pins,
      hidden_agents: local.hidden,
      hostname_override: local.hostnameOverride,
      agent_dropdowns: localDropdowns,
      theme: initialTheme(),
      theme_navbar_mode: initialNavbarThemeMode(),
      bubble_theme: loadBubbleTheme(),
      ...(localSections ? { rail_sections: localSections } : {}),
    })
    return { ...local, sections: localSections, source: 'import' }
  }
  return local
}
