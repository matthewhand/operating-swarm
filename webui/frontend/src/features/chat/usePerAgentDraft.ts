/**
 * #1331 — per-agent composer drafts.
 *
 * A draft typed for agent A must survive switching to agent B and back, and
 * must survive a remount (team picks route through `/teams/*` and remount
 * ChatPage). The draft map is therefore held in a module-level store backed by
 * localStorage: each agent id owns its own slot, and switching the active agent
 * only changes which slot is read — no other agent's slot is ever written.
 *
 * `usePerAgentDraft(agentId)` is a drop-in replacement for
 * `useState('')` at the composer's state owner:
 *
 *     const [input, setInput] = usePerAgentDraft(activeChatAgentId)
 *
 * `setInput` accepts a value or an updater function, matching React state, so
 * the existing `setInput('')` clears (send / Esc / slash) and
 * `setInput((prev) => prev + ch)` (voice / typing-anywhere) all keep working.
 * A clear is persisted (an explicit empty string), so a cleared draft can
 * never resurrect on switch-back or reload.
 *
 * Drafts are mirrored (debounced, best-effort) into the server prefs `values`
 * bag under `message_drafts` for cross-device restore, and seeded back from it
 * on first mount when this browser has no local drafts.
 */
import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react'
import { DEFAULT_AGENT_ID } from '../../lib/agentChat'
import { fetchUserPrefs, saveUserPrefs } from '../../lib/userPrefs'

export const AGENT_DRAFTS_STORAGE_KEY = 'os.agentMessageDrafts'
export const AGENT_DRAFTS_PREF_KEY = 'message_drafts'
/** Debounce window for the prefs-bag mirror (localStorage is written eagerly). */
export const AGENT_DRAFTS_PREFS_SYNC_MS = 800

export type AgentDraftMap = Record<string, string>

export function normalizeDraftAgentId(agentId: string | null | undefined): string {
  const id = (agentId ?? '').trim()
  return id || DEFAULT_AGENT_ID
}

function parseDraftMap(raw: unknown): AgentDraftMap {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const out: AgentDraftMap = {}
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof value !== 'string') continue
    out[normalizeDraftAgentId(key)] = value
  }
  return out
}

function readStoredDrafts(): AgentDraftMap {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(AGENT_DRAFTS_STORAGE_KEY)
    if (!raw) return {}
    return parseDraftMap(JSON.parse(raw))
  } catch {
    return {}
  }
}

let _drafts: AgentDraftMap = readStoredDrafts()
// useSyncExternalStore requires a stable snapshot reference between writes.
let _snapshot: AgentDraftMap = _drafts
const _listeners = new Set<() => void>()

function emit(): void {
  for (const listener of _listeners) listener()
}

function writeLocal(map: AgentDraftMap): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(AGENT_DRAFTS_STORAGE_KEY, JSON.stringify(map))
  } catch {
    /* private mode / quota — in-memory store still works for this session */
  }
}

let _prefsTimer: number | null = null

function schedulePrefsSync(): void {
  if (typeof window === 'undefined') return
  if (_prefsTimer !== null) window.clearTimeout(_prefsTimer)
  _prefsTimer = window.setTimeout(() => {
    _prefsTimer = null
    const payload = { ..._drafts }
    void saveUserPrefs({ values: { [AGENT_DRAFTS_PREF_KEY]: payload } }).catch(() => {
      /* best-effort: localStorage is the session source of truth */
    })
  }, AGENT_DRAFTS_PREFS_SYNC_MS)
}

function commit(next: AgentDraftMap, opts: { syncPrefs?: boolean } = {}): void {
  _drafts = next
  _snapshot = next
  writeLocal(next)
  emit()
  if (opts.syncPrefs !== false) schedulePrefsSync()
}

// Another tab writing the same key is adopted without an echo loop.
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event) => {
    if (event.key !== AGENT_DRAFTS_STORAGE_KEY) return
    const next = readStoredDrafts()
    _drafts = next
    _snapshot = next
    emit()
  })
}

export function getAgentDraftMap(): AgentDraftMap {
  return _snapshot
}

export function getAgentDraft(agentId: string | null | undefined): string {
  return _snapshot[normalizeDraftAgentId(agentId)] ?? ''
}

/** Persist one agent's draft. Never touches any other agent's slot. */
export function setAgentDraft(agentId: string | null | undefined, value: string): void {
  const id = normalizeDraftAgentId(agentId)
  if ((_drafts[id] ?? '') === value) return
  commit({ ..._drafts, [id]: value })
}

/** Persist an explicit clear so a stale value can never resurface. */
export function clearAgentDraft(agentId: string | null | undefined): void {
  setAgentDraft(agentId, '')
}

export function subscribeAgentDrafts(listener: () => void): () => void {
  _listeners.add(listener)
  return () => {
    _listeners.delete(listener)
  }
}

let _hydrateStarted = false

/**
 * One-shot seed from the server prefs `values` bag. Local drafts always win;
 * the bag only fills slots this browser has never seen. Runs at most once per
 * module lifetime and never throws.
 */
function hydrateDraftsFromPrefs(): void {
  if (_hydrateStarted) return
  _hydrateStarted = true
  if (typeof window === 'undefined') return
  if (Object.keys(_drafts).length > 0) return
  void fetchUserPrefs()
    .then((prefs) => {
      const seed = parseDraftMap(prefs?.values?.[AGENT_DRAFTS_PREF_KEY])
      if (Object.keys(seed).length === 0) return
      commit({ ...seed, ..._drafts }, { syncPrefs: false })
    })
    .catch(() => {
      /* offline / throttled: localStorage remains authoritative */
    })
}

/** Subscribe to the whole per-agent map (used to keep one input per agent). */
export function useAllAgentDrafts(): AgentDraftMap {
  useEffect(() => {
    hydrateDraftsFromPrefs()
  }, [])
  return useSyncExternalStore(subscribeAgentDrafts, getAgentDraftMap, getAgentDraftMap)
}

export type PerAgentDraftSetter = (value: string | ((prev: string) => string)) => void

/**
 * Read/write the active agent's draft. Drop-in for `useState('')` at the
 * composer state owner so every existing `setInput(...)` call is scoped to the
 * agent that is active when the call is made.
 */
export function usePerAgentDraft(
  agentId: string | null | undefined,
): [string, PerAgentDraftSetter] {
  const id = normalizeDraftAgentId(agentId)
  const drafts = useSyncExternalStore(subscribeAgentDrafts, getAgentDraftMap, getAgentDraftMap)
  useEffect(() => {
    hydrateDraftsFromPrefs()
  }, [])
  const idRef = useRef(id)
  idRef.current = id
  const setValue = useCallback<PerAgentDraftSetter>((next) => {
    const target = idRef.current
    const resolved =
      typeof next === 'function' ? next(getAgentDraft(target)) : next
    setAgentDraft(target, resolved)
  }, [])
  return [drafts[id] ?? '', setValue]
}

/** Test isolation only: drop the module store back to a clean slate. */
export function __resetAgentDraftsForTests(): void {
  if (_prefsTimer !== null) {
    clearTimeout(_prefsTimer)
    _prefsTimer = null
  }
  _drafts = {}
  _snapshot = _drafts
  _hydrateStarted = false
  try {
    window.localStorage.removeItem(AGENT_DRAFTS_STORAGE_KEY)
  } catch {
    /* ignore */
  }
  emit()
}
