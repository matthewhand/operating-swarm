/**
 * #550: what the composer `+` menu may offer, derived from the seat.
 *
 * The menu used to be hand-written JSX in which each item gated itself — or, in
 * the case of `Compact`, did not gate at all. `Compact` rendered for every seat
 * kind even though it summarises **server-side** conversation history, which a
 * CLI or remote seat does not have: the transcript belongs to the provider. That
 * is the same defect class as #534, which had already restricted compression
 * *notifications* to the API subclass while leaving the action itself available.
 *
 * So the capabilities live here, keyed by a declared id union. Adding an item to
 * {@link COMPOSER_MENU_ITEM_IDS} without giving it a capability is a **type
 * error** (`Record<ComposerMenuItemId, …>`), which is what makes "a future item
 * cannot repeat this by omission" true rather than aspirational.
 *
 * #1230: an unavailable action is **absent**, not greyed. `Compact` in
 * particular is API-only and never renders a disabled/"not available" state on
 * a CLI, remote, or unresolved seat — the user reports in #1230 were all that
 * state. `Add files` / `Plugins` keep the earlier #511 visible-but-disabled
 * precedent because their reasons are actionable (configure an API, use a
 * swarm seat); a CLI seat cannot acquire a compact at all.
 *
 * #1725: `defaultLlmReady` was **deleted from this interface**, not wired up.
 * It had been declared here since #636 and read by nothing — `Compact` is gated
 * on the positive `isApi` alone (#1230), and a configured default API cannot
 * give a CLI seat a transcript to compact. Leaving it advertised a gate that
 * did not exist. The *observable* it stood for is still reported where it is
 * real: `/v1/llm-profiles/` `default_llm_ready` drives `DefaultLlmTip`
 * (`lib/defaultLlmTip.ts`), which is the surface that actually tells an operator
 * their default profile is unusable.
 */

import { composerFileAttachSupported } from './chatAttachments'

/** Every id the composer `+` menu can render. One union, one owner. */
export const COMPOSER_MENU_ITEM_IDS = ['addFiles', 'compact', 'plugins', 'rewrite'] as const

export type ComposerMenuItemId = (typeof COMPOSER_MENU_ITEM_IDS)[number]

export interface ComposerMenuSeat {
  /** A seat the backend runs (API / blueprint). */
  isApi?: boolean
  isCli?: boolean
  isRemote?: boolean
  /** #636: the CLI provider declares a native `cli_compact` hook (catalog `cli_compact`). */
  cliCompactCapable?: boolean
  /** #830: display name of the remote provider (e.g. "Herdr", "TrueForge"). */
  providerName?: string
  /** #830: the remote provider declares a native compact hook — the remote
   * analogue of `cliCompactCapable`. */
  remoteCompactCapable?: boolean
  /** #516: the seat passes the swarm-owned plugins gate (#511's predicate). */
  pluginsSwarmOwned?: boolean
  /** #551: the kind base's declared capabilities, published as data by
   * `GET /v1/cli-agents/` (`seat_capabilities`). When absent (older backend),
   * the menu falls back to the kind-derived gates below. */
  declaredCapabilities?: Record<string, { enabled: boolean; reason: string }>
}

/** #551: read one declared capability; `undefined` when not published. */
export function declaredCapability(
  seat: ComposerMenuSeat | undefined,
  name: string,
): { enabled: boolean; reason: string } | undefined {
  return seat?.declaredCapabilities?.[name]
}

export interface ComposerMenuItemCapability {
  enabled: boolean
  /** Why the action is offered but unusable. Shown as the item's `title`. */
  reason: string
}

export type ComposerMenuCapabilities = Record<ComposerMenuItemId, ComposerMenuItemCapability>

export const ATTACH_DISABLED_REASON =
  'File attachments aren’t supported for CLI or remote seats'

export const COMPACT_DISABLED_REASON =
  'Compact is API-only — CLI and remote seats keep their transcript in the provider'

/** #1230: kept for payload/test consumers; no rendered item uses it any more
 * because an unavailable Compact is never drawn. */
export const COMPACT_NO_API_REASON =
  'Compact is API-only — CLI seats have no server-side history to summarise'

/** #830: kept for payload/test consumers; the remote Compact item is absent,
 * not disabled, since #1230. */
export function compactRemoteReason(providerName?: string): string {
  return `Compact is not implemented for ${providerName?.trim() || 'this provider'}`
}

/** #516: Plugins ride the swarm-owned reading of #511 (API + blueprint seats) —
 * the same predicate the rail's Plugins entry and the badge gate on. */
export const PLUGINS_DISABLED_REASON =
  'Plugins are available on API and blueprint seats — CLI and remote seats run their tools on the provider'

/**
 * #1220: the rewrite action fires auxiliary LLM inference on every use, so it
 * is an opt-in affordance. Unlike the other items it does not render greyed
 * with a reason — disabled means ABSENT: an always-visible item would invite
 * accidental spends, and there is no seat state that can flip it back on.
 * The gate is the operator preference (`swarm_composer_rewrite_enabled`).
 */
export const REWRITE_DISABLED_REASON =
  'AI prompt rewrite is off — enable it in Settings → General'

export function composerMenuCapabilities(seat: ComposerMenuSeat & { rewriteEnabled?: boolean }): ComposerMenuCapabilities {
  // One owner for the attach rule: the same helper the composer uses to decide
  // whether the paperclip is live, so the menu cannot disagree with the input.
  const addFiles = composerFileAttachSupported({
    isCli: seat.isCli,
    isRemote: seat.isRemote,
  })
  // Compact is API-only. `isApi` is the deliberate gate rather than
  // `!isCli && !isRemote`, because a seat that is none of the three (an
  // unresolved blueprint, say) must not silently gain the action. CLI / remote
  // seats serve their transcript from the provider, so there is no compact for
  // the swarm to offer them — they get no item at all, never a disabled one.
  const compact = Boolean(seat.isApi)
  // #1230: an unavailable compact is NOT an affordance. The item is
  // enabled-or-absent (same contract as #1220's rewrite), so no seat ever
  // renders a disabled/"not available" Compact. The reason is retained only
  // for the (never-rendered) absent case and for capability payload consumers.
  // #516: the Plugins entry uses the same swarm-owned reading (#511) the rail
  // footer and the badge already gate on — one predicate, three consumers.
  const plugins = Boolean(seat.pluginsSwarmOwned)
  // #1220: rewrite is operator-opt-in (single boolean, tier-independent —
  // the aux-inference cost concern is not a viewport concern). Default OFF.
  const rewrite = Boolean(seat.rewriteEnabled)
  // #551: a published declaration outranks every kind-derived gate. When the
  // backend has not published one, the local predicates above remain the
  // fallback so an older payload cannot silently widen a seat's powers.
  const declaredPlugins = declaredCapability(seat, 'plugins')
  const declaredAttach = declaredCapability(seat, 'attach')
  const declaredRewrite = declaredCapability(seat, 'rewrite')
  return {
    addFiles: declaredAttach ?? { enabled: addFiles, reason: ATTACH_DISABLED_REASON },
    compact: { enabled: compact, reason: compact ? '' : COMPACT_DISABLED_REASON },
    plugins: declaredPlugins ?? { enabled: plugins, reason: PLUGINS_DISABLED_REASON },
    rewrite: declaredRewrite ?? { enabled: rewrite, reason: REWRITE_DISABLED_REASON },
  }
}
