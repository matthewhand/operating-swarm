/**
 * REQ-853 / #207 — dismissable chat-pane tip when an API/blueprint seat runs
 * on the default LLM profile but no usable default LLM is configured.
 *
 * Mirrors the roleAgentTip (REQ-191) pattern: localStorage is immediate,
 * Django prefs extras sync when /v1/preferences/ is available. The tip never
 * blocks sending — the turn still surfaces the real resolver error if the
 * host is misconfigured.
 */

import { fetchUserPrefs, saveUserPrefs } from './userPrefs'

export const DEFAULT_LLM_TIP_STORAGE_KEY = 'swarm_default_llm_tip_dismissed'
export const DEFAULT_LLM_TIP_PREF_KEY = 'default_llm_tip_dismissed'

export const DEFAULT_LLM_TIP_TITLE = 'This agent has no LLM configured yet'
export const DEFAULT_LLM_TIP_BODY =
  'This agent uses the default LLM profile, which is not usable right now — no API key or custom endpoint resolves for it. You can still send messages; configure the default profile in Settings to make this agent work.'

export interface DefaultLlmTipOptions {
  /** API/blueprint seat (not team, remote, or CLI — those never use swarm LLM config). */
  isApiAgent: boolean
  /** Explicit model/profile override on the seat or URL — a pinned seat is not unconfigured. */
  hasExplicitModelOverride?: boolean
  /** From /v1/llm-profiles/ payload (`default_llm_ready`). Undefined (older server) → no tip. */
  defaultLlmReady?: boolean
  dismissed?: boolean
}

export function shouldShowDefaultLlmTip(opts: DefaultLlmTipOptions): boolean {
  if (opts.dismissed) return false
  if (!opts.isApiAgent) return false
  if (opts.hasExplicitModelOverride) return false
  // Undefined means the server predates the flag: stay silent rather than
  // nag on an unknown state.
  if (opts.defaultLlmReady !== false) return false
  return true
}

export function isDefaultLlmTipDismissed(): boolean {
  try {
    return localStorage.getItem(DEFAULT_LLM_TIP_STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export function prefsDefaultLlmTipDismissed(
  prefs: { values?: Record<string, unknown> } | null | undefined,
): boolean {
  return prefs?.values?.[DEFAULT_LLM_TIP_PREF_KEY] === true
}

export function persistDefaultLlmTipDismissedLocal(): void {
  try {
    localStorage.setItem(DEFAULT_LLM_TIP_STORAGE_KEY, '1')
  } catch {
    /* persistence is best-effort */
  }
}

export async function persistDefaultLlmTipDismissed(): Promise<void> {
  persistDefaultLlmTipDismissedLocal()
  await saveUserPrefs({ values: { [DEFAULT_LLM_TIP_PREF_KEY]: true } })
}

/**
 * Server bag wins when it has dismissed=true. Local dismiss imports once
 * if the extras key is missing.
 */
export async function hydrateDefaultLlmTipDismissed(): Promise<boolean> {
  const local = isDefaultLlmTipDismissed()
  const server = await fetchUserPrefs()
  if (!server) return local
  if (prefsDefaultLlmTipDismissed(server)) {
    persistDefaultLlmTipDismissedLocal()
    return true
  }
  const extras = server.values || {}
  const missing = extras[DEFAULT_LLM_TIP_PREF_KEY] === undefined
  if (local && (server.empty || missing)) {
    await saveUserPrefs({ values: { [DEFAULT_LLM_TIP_PREF_KEY]: true } })
  }
  return local
}
