/**
 * #1202 — navbar picker hide toggles.
 *
 * Two independent booleans let a power user **unmount** the navbar Agent /
 * Session selector when the active seat cannot support it, instead of leaving
 * it visible-but-greyed. Persisted to `/v1/preferences/` (registry keys
 * `hide_unsupported_agent_picker` / `hide_unsupported_session_picker`,
 * defaults `false`); localStorage is the immediate cache so the header reacts
 * without waiting on the round-trip.
 */
import { saveUserPrefs, type UserPrefs } from './userPrefs'

export const HIDE_UNSUPPORTED_AGENT_PICKER_KEY = 'hide_unsupported_agent_picker'
export const HIDE_UNSUPPORTED_SESSION_PICKER_KEY = 'hide_unsupported_session_picker'
export const NAVBAR_PICKER_PREFS_CHANGED_EVENT = 'swarm:navbar-picker-prefs-changed'

export interface NavbarPickerPrefs {
  hideUnsupportedAgentPicker: boolean
  hideUnsupportedSessionPicker: boolean
}

const STORAGE_KEY = 'swarm:navbar-picker-prefs'

export const DEFAULT_NAVBAR_PICKER_PREFS: NavbarPickerPrefs = {
  hideUnsupportedAgentPicker: false,
  hideUnsupportedSessionPicker: false,
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
}

function readFlag(rec: Record<string, unknown>, values: Record<string, unknown>, key: string): boolean {
  const raw = rec[key] !== undefined ? rec[key] : values[key]
  return raw === true || raw === 'true' || raw === 1 || raw === '1'
}

/** Read the two flags from a server bag or a local cached object. */
export function parseNavbarPickerPrefs(raw: unknown): NavbarPickerPrefs {
  const rec = asRecord(raw)
  const values = asRecord(rec.values)
  return {
    hideUnsupportedAgentPicker: readFlag(rec, values, HIDE_UNSUPPORTED_AGENT_PICKER_KEY),
    hideUnsupportedSessionPicker: readFlag(rec, values, HIDE_UNSUPPORTED_SESSION_PICKER_KEY),
  }
}

export function loadNavbarPickerPrefs(): NavbarPickerPrefs {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT_NAVBAR_PICKER_PREFS }
    const rec = asRecord(JSON.parse(raw))
    // The cache is written in the camelCase shape; tolerate a server-shaped
    // bag too (snake_case keys) so either source hydrates.
    if ('hideUnsupportedAgentPicker' in rec || 'hideUnsupportedSessionPicker' in rec) {
      return {
        hideUnsupportedAgentPicker: rec.hideUnsupportedAgentPicker === true,
        hideUnsupportedSessionPicker: rec.hideUnsupportedSessionPicker === true,
      }
    }
    return parseNavbarPickerPrefs(rec)
  } catch {
    return { ...DEFAULT_NAVBAR_PICKER_PREFS }
  }
}

function dispatchChanged(): void {
  try {
    window.dispatchEvent(new CustomEvent(NAVBAR_PICKER_PREFS_CHANGED_EVENT))
  } catch {
    /* ignore environments without window */
  }
}

/** Write the local cache only — no server PATCH, no event (hydrate path). */
export function cacheNavbarPickerPrefs(next: NavbarPickerPrefs): NavbarPickerPrefs {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {
    /* ignore quota / disabled storage */
  }
  return next
}

function persist(next: NavbarPickerPrefs): NavbarPickerPrefs {
  cacheNavbarPickerPrefs(next)
  dispatchChanged()
  void saveUserPrefs({
    values: {
      [HIDE_UNSUPPORTED_AGENT_PICKER_KEY]: next.hideUnsupportedAgentPicker,
      [HIDE_UNSUPPORTED_SESSION_PICKER_KEY]: next.hideUnsupportedSessionPicker,
    },
  })
  return next
}

export function saveHideUnsupportedAgentPicker(value: boolean): NavbarPickerPrefs {
  return persist({ ...loadNavbarPickerPrefs(), hideUnsupportedAgentPicker: value })
}

export function saveHideUnsupportedSessionPicker(value: boolean): NavbarPickerPrefs {
  return persist({ ...loadNavbarPickerPrefs(), hideUnsupportedSessionPicker: value })
}

/** Adopt the server bag's values (server wins on hydrate). */
export function applyNavbarPickerPrefsFromUserPrefs(
  prefs: UserPrefs | null | undefined,
): NavbarPickerPrefs {
  const next = cacheNavbarPickerPrefs(parseNavbarPickerPrefs(prefs ?? {}))
  dispatchChanged()
  return next
}
