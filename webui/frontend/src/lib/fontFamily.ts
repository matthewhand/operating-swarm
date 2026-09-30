/**
 * #1227 — interface font family preference.
 *
 * Presets are applied through the root `--os-font-family` CSS variable (see
 * index.css); the active preset is mirrored to a `data-os-font` attribute for
 * inspection/testing. localStorage caches the choice for flicker-free boot and
 * the Django preferences `values` bag syncs it across devices (userPrefs.ts).
 *
 * The default is the Omarchy-compatible stack (JetBrainsMono Nerd Font with a
 * system-ui fallback): Omarchy/Arch hosts ship that font, and it degrades
 * gracefully to the platform UI font elsewhere.
 */

export type FontFamilyId = 'omarchy' | 'hack' | 'monospace' | 'sans' | 'serif' | 'custom'

/** Ticket default — JetBrainsMono Nerd Font first, system sans fallback. */
export const DEFAULT_FONT_FAMILY: FontFamilyId = 'omarchy'

export const FONT_FAMILY_STORAGE_KEY = 'swarm_font_family'
/** Operator-supplied stack backing the `custom` preset. */
export const CUSTOM_FONT_FAMILY_STORAGE_KEY = 'swarm_font_family_custom'
/** Fired by saveFontFamily / saveCustomFontFamily so surfaces re-read live. */
export const FONT_FAMILY_CHANGED_EVENT = 'swarm:font-family-changed'

/** Root CSS variable consumed by the base rule in index.css. */
export const OS_FONT_FAMILY_VAR = '--os-font-family'
/** Root attribute mirroring the active preset (inspectable / testable). */
export const OS_FONT_FAMILY_ATTR = 'data-os-font'

export const FONT_FAMILIES: FontFamilyId[] = [
  'omarchy',
  'hack',
  'monospace',
  'sans',
  'serif',
  'custom',
]

export const FONT_FAMILY_LABELS: Record<FontFamilyId, string> = {
  omarchy: 'Omarchy / System (default)',
  hack: 'Hack',
  monospace: 'Monospace',
  sans: 'Sans-Serif',
  serif: 'Serif',
  custom: 'Custom',
}

export const FONT_FAMILY_STACKS: Record<Exclude<FontFamilyId, 'custom'>, string> = {
  omarchy:
    "'JetBrainsMono Nerd Font', 'JetBrains Mono', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  hack: "'Hack', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace",
  monospace:
    "'JetBrainsMono Nerd Font', 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace",
  sans: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', Ubuntu, Cantarell, sans-serif",
  serif: "ui-serif, Georgia, Cambria, 'Times New Roman', Times, serif",
}

export const CUSTOM_FONT_FAMILY_MAX_LEN = 160

const KNOWN_IDS = new Set<string>(FONT_FAMILIES)
/** Legacy id persisted by the first cut of #1227 — folds into the default. */
const LEGACY_SYSTEM_ID = 'system'

/** Resolve a stored patched value to a preset id (unknown strings → custom). */
export function parseFontFamily(raw: unknown): FontFamilyId {
  if (typeof raw === 'string') {
    const value = raw.trim()
    if (KNOWN_IDS.has(value)) return value as FontFamilyId
    if (value === LEGACY_SYSTEM_ID) return DEFAULT_FONT_FAMILY
    if (value.length > 0) return 'custom'
  }
  return DEFAULT_FONT_FAMILY
}

/** True when `raw` names a preset (including the legacy `system` id). */
export function isFontFamilyPreset(raw: unknown): boolean {
  if (typeof raw !== 'string') return false
  const value = raw.trim()
  return KNOWN_IDS.has(value) || value === LEGACY_SYSTEM_ID
}

/**
 * Sanitize an operator-supplied font-family stack: drop control characters
 * and CSS-structural punctuation that could break the declaration, then cap
 * the length. Quotes, commas, hyphens and spaces are preserved.
 */
export function normalizeCustomFontFamily(raw: unknown): string {
  if (typeof raw !== 'string') return ''
  return raw
    .replace(/[\u0000-\u001f\u007f]/g, '')
    .replace(/[;{}<>\\]/g, '')
    .trim()
    .slice(0, CUSTOM_FONT_FAMILY_MAX_LEN)
}

export function loadCustomFontFamily(): string {
  try {
    return normalizeCustomFontFamily(localStorage.getItem(CUSTOM_FONT_FAMILY_STORAGE_KEY))
  } catch {
    return ''
  }
}

export function loadFontFamily(): FontFamilyId {
  try {
    return parseFontFamily(localStorage.getItem(FONT_FAMILY_STORAGE_KEY))
  } catch {
    return DEFAULT_FONT_FAMILY
  }
}

/** Resolved CSS stack for the active selection (custom reads its own value). */
export function currentFontFamilyStack(): string {
  const id = loadFontFamily()
  if (id === 'custom') return loadCustomFontFamily()
  return FONT_FAMILY_STACKS[id]
}

/**
 * Set (or, for an empty custom stack, clear) the root variable + attribute.
 * With no argument the persisted selection is applied (boot / cross-tab).
 */
export function applyFontFamily(raw?: unknown, custom?: string): FontFamilyId {
  const id = raw === undefined ? loadFontFamily() : parseFontFamily(raw)
  const stack =
    id === 'custom'
      ? normalizeCustomFontFamily(custom ?? loadCustomFontFamily())
      : FONT_FAMILY_STACKS[id]
  if (typeof document === 'undefined') return id
  const root = document.documentElement
  if (stack) {
    root.style.setProperty(OS_FONT_FAMILY_VAR, stack)
    root.setAttribute(OS_FONT_FAMILY_ATTR, id)
  } else {
    root.style.removeProperty(OS_FONT_FAMILY_VAR)
    root.removeAttribute(OS_FONT_FAMILY_ATTR)
  }
  return id
}

function emitFontFamilyChanged(id: FontFamilyId): void {
  try {
    window.dispatchEvent(new CustomEvent(FONT_FAMILY_CHANGED_EVENT, { detail: id }))
  } catch {
    /* tests / non-browser */
  }
}

/** Select a preset (or a raw custom stack) and apply it immediately. */
export function saveFontFamily(value: unknown): FontFamilyId {
  if (typeof value === 'string' && value.trim() && !isFontFamilyPreset(value)) {
    return saveCustomFontFamily(value)
  }
  const id = parseFontFamily(value)
  try {
    localStorage.setItem(FONT_FAMILY_STORAGE_KEY, id)
  } catch {
    /* persistence is best-effort */
  }
  applyFontFamily(id)
  emitFontFamilyChanged(id)
  return id
}

/** Store the operator's custom stack and select the `custom` preset. */
export function saveCustomFontFamily(value: unknown): FontFamilyId {
  const cleaned = normalizeCustomFontFamily(value)
  try {
    if (cleaned) localStorage.setItem(CUSTOM_FONT_FAMILY_STORAGE_KEY, cleaned)
    else localStorage.removeItem(CUSTOM_FONT_FAMILY_STORAGE_KEY)
    localStorage.setItem(FONT_FAMILY_STORAGE_KEY, 'custom')
  } catch {
    /* persistence is best-effort */
  }
  applyFontFamily('custom', cleaned)
  emitFontFamilyChanged('custom')
  return 'custom'
}
