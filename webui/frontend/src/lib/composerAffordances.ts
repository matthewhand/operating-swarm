/**
 * #1215 / #1219 / #1220 — composer affordance visibility preferences.
 *
 * Two opt-in surfaces share this module:
 *
 * 1. **Provider dropdown** (#1215 general toggle, #1219 mobile default-off):
 *    the composer's provider/model routing picker. #878 made it a plain
 *    boolean (default visible everywhere); #1219 demotes mobile to hidden
 *    unless the user explicitly opts in per viewport tier (#833), and
 *    #1215 adds the general switch behind it. Resolution: an explicit tier
 *    override wins; otherwise the tier default (mobile hidden, tablet and
 *    desktop visible per #878's shipped behavior).
 *
 * 2. **AI prompt rewrite** (#1220): the composer `+` menu's "Rewrite prompt
 *    with AI" action. Disabled (menu item absent) by default — it fires
 *    auxiliary LLM inference per use, so it must be a deliberate opt-in.
 *    A single boolean (not tiered): the cost concern is tier-independent.
 *
 * Storage + CustomEvent pattern mirrors `composerShowProvider.ts` so
 * ChatPage reacts without a reload.
 */
import {
  currentViewportTier,
  type ResponsivePref,
  type ViewportTier,
} from './responsivePrefs'

export const COMPOSER_SHOW_PROVIDER_TIERS_KEY = 'swarm_composer_show_provider_tiers'
export const COMPOSER_SHOW_PROVIDER_TIERS_EVENT = 'swarm:set-composer-show-provider-tiers'
export const COMPOSER_REWRITE_ENABLED_KEY = 'swarm_composer_rewrite_enabled'
export const COMPOSER_REWRITE_ENABLED_EVENT = 'swarm:set-composer-rewrite-enabled'

/**
 * #1219: mobile ships hidden. Tablet/desktop keep #878's visible default —
 * the dropdown earned its place there; on a phone it eats the composer.
 */
export const DEFAULT_SHOW_PROVIDER_TIERS: ResponsivePref<boolean> = {
  mobile: false,
  tablet: true,
  desktop: true,
}

function readBooleanList(raw: string | null): Partial<ResponsivePref<boolean>> | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    if (typeof parsed === 'object' && parsed !== null) return parsed
  } catch {
    /* corrupt value — fall through to defaults */
  }
  return null
}

export function loadShowProviderTiers(): ResponsivePref<boolean> {
  let stored: Partial<ResponsivePref<boolean>> | null = null
  try {
    stored = readBooleanList(localStorage.getItem(COMPOSER_SHOW_PROVIDER_TIERS_KEY))
  } catch {
    /* storage unavailable */
  }
  // #878 compatibility: a legacy boolean value seeds every tier the user had
  // visible; a legacy 'false' stays hidden everywhere.
  try {
    if (!stored) {
      const legacy = localStorage.getItem('swarm_composer_show_provider')
      if (legacy === 'false') stored = { mobile: false, tablet: false, desktop: false }
      else if (legacy === 'true') stored = { mobile: true, tablet: true, desktop: true }
    }
  } catch {
    /* storage unavailable */
  }
  return {
    mobile: stored?.mobile ?? DEFAULT_SHOW_PROVIDER_TIERS.mobile,
    tablet: stored?.tablet ?? DEFAULT_SHOW_PROVIDER_TIERS.tablet,
    desktop: stored?.desktop ?? DEFAULT_SHOW_PROVIDER_TIERS.desktop,
  }
}

/** The resolved visibility for the tier the user is actually in right now. */
export function currentShowProviderResolved(tier?: ViewportTier): boolean {
  const resolved = loadShowProviderTiers()
  return resolved[tier ?? currentViewportTier()]
}

export function saveShowProviderTiers(pref: ResponsivePref<boolean>): ResponsivePref<boolean> {
  try {
    localStorage.setItem(COMPOSER_SHOW_PROVIDER_TIERS_KEY, JSON.stringify(pref))
    window.dispatchEvent(new CustomEvent(COMPOSER_SHOW_PROVIDER_TIERS_EVENT))
  } catch {
    /* persistence is best-effort */
  }
  return { ...pref }
}

export function loadRewriteEnabled(): boolean {
  try {
    return localStorage.getItem(COMPOSER_REWRITE_ENABLED_KEY) === 'true'
  } catch {
    return false
  }
}

export function saveRewriteEnabled(enabled: boolean): boolean {
  try {
    localStorage.setItem(COMPOSER_REWRITE_ENABLED_KEY, String(enabled))
    window.dispatchEvent(new CustomEvent(COMPOSER_REWRITE_ENABLED_EVENT, { detail: enabled }))
  } catch {
    /* persistence is best-effort */
  }
  return enabled
}
