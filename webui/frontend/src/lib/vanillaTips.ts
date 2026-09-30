/**
 * #1700 (3) — the first-run chat tip whose fact the server emits and nothing in
 * the SPA was reading.
 *
 * `GET /v1/support/context/` answers `inference.configured`: on a fresh install
 * with no provider it is `false`, and every API/blueprint seat then fails its
 * first turn. Before this module that fact had **no SPA consumer at all**
 * (`fetchSupportContext()` was never called) — the endpoint was serialised for
 * nobody. This module is that consumer's policy.
 *
 * #1703 (a CLI on PATH that is not wired up) is deliberately NOT re-implemented
 * here. That condition already ships as `lib/hostCliTip.ts` + `HostCliTip`,
 * which owns it outright: a wiring hint reading the same `/v1/cli-agents/`
 * payload must not be forked into a second renderer with a second dismissal
 * key. What this module owes that one is EXCLUSIVITY, so the two never explain
 * the same "you cannot talk to anything yet" twice — see `firstVanillaTip`.
 *
 * Two rules this module exists to keep:
 *
 * 1. **At most one tip.** Two signals with two independent renderers is the
 *    "worst of both" #1725 warns about: a duplicate is a second thing to
 *    dismiss and a second chance to be wrong. `firstVanillaTip` returns at most
 *    one tip, by declared priority.
 * 2. **A tip that can be wrong is worse than no tip.** Every input is read
 *    fail-open — an absent payload, a failed request, or a field the server
 *    does not send yields *no tip*, never a speculative one. And the tip stands
 *    down when `default_llm_ready === false`, because the pre-existing
 *    seat-scoped `DefaultLlmTip` already owns that explanation; two tips for
 *    one condition is the duplicate rule (1).
 *
 * Dismissal is **persisted** through the existing preferences store
 * (`/v1/preferences/` `values` bag + a localStorage mirror), the same store
 * `DefaultLlmTip` and the role tip use. A dismissal that only lived in
 * component state would reappear on every reload — which is the same defect
 * class as the rest of this batch.
 */

import type { CliAgentsInfo, SupportContext } from './api'
import { hostCliDetectedName } from './hostCliTip'
import { fetchUserPrefs, saveUserPrefs, type UserPrefs } from './userPrefs'

export const CONFIGURE_API_TIP_ID = 'configure-api'

/** Pref-bag key per tip id. Namespaced so a future tip cannot collide. */
export const VANILLA_TIP_PREF_KEYS: Record<string, string> = {
  [CONFIGURE_API_TIP_ID]: 'vanilla_tip_configure_api_dismissed',
}

export const VANILLA_TIP_STORAGE_PREFIX = 'swarm_vanilla_tip_dismissed_'

/** Settings deep link. The same href `lib/settingsLinks.ts` intercepts, so a
 *  link in chat opens the sheet instead of navigating. */
export const CONFIGURE_API_HREF = '/chat?settings=llm-profiles'

export interface VanillaTip {
  id: string
  title: string
  body: string
  /** In-product route that repairs the condition. Never a dead-end string. */
  cta: { href: string; label: string }
}

function configureApiTip(): VanillaTip {
  return {
    id: CONFIGURE_API_TIP_ID,
    title: 'No LLM provider is set up yet',
    body:
      'Add an API provider to chat with the API and blueprint agents. A CLI ' +
      'agent on your PATH works without one.',
    cta: { href: CONFIGURE_API_HREF, label: 'Set up an API provider' },
  }
}

export interface FirstVanillaTipInput {
  /** `GET /v1/support/context/`. Absent / failed → contributes nothing. */
  supportContext?: SupportContext | null
  /** `GET /v1/cli-agents/`. Absent / failed → contributes nothing. Read ONLY to
   *  stand down for the host-CLI tip; that tip's own renderer owns the CLI
   *  condition, so this module never describes a CLI. */
  cliAgents?: CliAgentsInfo | null
  /** `GET /v1/llm-profiles/` `default_llm_ready`. `false` = another owner. */
  defaultLlmReady?: boolean
  /** Tip ids the operator has already dismissed (any source). */
  dismissedIds?: readonly string[]
}

/**
 * The one tip to render, or `null`. Priority is declared, not emergent.
 */
export function firstVanillaTip(input: FirstVanillaTipInput): VanillaTip | null {
  // Rule 1, against the OTHER first-run tip (#1703, `lib/hostCliTip.ts`). This
  // calls that module's own detector, so the two can never disagree about
  // whether a CLI is waiting: if one names a CLI, that tip owns the slot and
  // this one stands down. A detected CLI is also the *cheaper* fix — wiring it
  // needs no API key — so leading with "set up an API provider" would ask for
  // the harder thing first on exactly the greenfield host both tips are for.
  if (hostCliDetectedName(input.cliAgents)) return null

  const dismissed = new Set(input.dismissedIds ?? [])
  const inference = input.supportContext?.inference
  if (
    inference &&
    inference.configured === false &&
    // #1700 (3) with the honest exemption: when the server says the *default*
    // profile itself is unusable, the pre-existing seat-scoped DefaultLlmTip
    // already explains it. Standing down keeps one condition to one tip.
    input.defaultLlmReady !== false &&
    !dismissed.has(CONFIGURE_API_TIP_ID)
  ) {
    return configureApiTip()
  }

  return null
}

// --- dismissal persistence, per tip id, through the existing prefs store ---

export function tipStorageKey(id: string): string {
  return `${VANILLA_TIP_STORAGE_PREFIX}${id}`
}

export function tipPrefKey(id: string): string {
  return VANILLA_TIP_PREF_KEYS[id] ?? `vanilla_tip_${id}_dismissed`
}

export function isVanillaTipDismissedLocal(id: string): boolean {
  try {
    return localStorage.getItem(tipStorageKey(id)) === '1'
  } catch {
    return false
  }
}

export function persistVanillaTipDismissedLocal(id: string): void {
  try {
    localStorage.setItem(tipStorageKey(id), '1')
  } catch {
    /* persistence is best-effort */
  }
}

/** Persist a dismissal so it survives a reload. Server first, local mirror. */
export async function persistVanillaTipDismissed(id: string): Promise<void> {
  persistVanillaTipDismissedLocal(id)
  await saveUserPrefs({ values: { [tipPrefKey(id)]: true } })
}

function prefsDismissed(prefs: UserPrefs | null | undefined, id: string): boolean {
  return prefs?.values?.[tipPrefKey(id)] === true
}

/**
 * Local ∪ server, with a one-way import of a local dismissal into a server bag
 * that has never seen it. Union, not "server wins": a dismissal is a promise
 * about the operator's intent, and dropping it because a pref read was slow
 * would put the tip back on screen.
 */
export async function hydrateVanillaTipDismissals(ids: readonly string[]): Promise<string[]> {
  const local = ids.filter((id) => isVanillaTipDismissedLocal(id))
  if (local.length === 0) return []
  // Both the read and the one-way import are guarded: this hydrator is called
  // from a mount effect with no `.catch()`, so a rejected promise here is an
  // unhandled rejection in the page. A dismissal is a promise about intent —
  // losing it because a pref read or write failed puts the tip back on screen.
  let server: UserPrefs | null = null
  try {
    server = await fetchUserPrefs()
  } catch {
    return local
  }
  if (!server) return local
  const needsImport = local.filter((id) => !prefsDismissed(server, id))
  if (needsImport.length > 0 && server.empty) {
    try {
      await saveUserPrefs({
        values: Object.fromEntries(needsImport.map((id) => [tipPrefKey(id), true])),
      })
    } catch {
      /* the local mirror already carries it */
    }
  }
  return local
}
