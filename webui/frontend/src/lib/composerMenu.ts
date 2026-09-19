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
 * Disabled items stay **visible** with a reason rather than disappearing: the
 * user has just opened this menu, and #511 set the precedent that the reason is
 * reachable (and is what the `Add files` item already does).
 */

import { composerFileAttachSupported } from './chatAttachments'

/** Every id the composer `+` menu can render. One union, one owner. */
export const COMPOSER_MENU_ITEM_IDS = ['addFiles', 'compact', 'plugins'] as const

export type ComposerMenuItemId = (typeof COMPOSER_MENU_ITEM_IDS)[number]

export interface ComposerMenuSeat {
  /** A seat the backend runs (API / blueprint). */
  isApi?: boolean
  isCli?: boolean
  isRemote?: boolean
  /** #636: a default API profile is configured (`/v1/llm-profiles/` `default_llm_ready`). */
  defaultLlmReady?: boolean
  /** #636: the CLI provider declares a native `cli_compact` hook (catalog `cli_compact`). */
  cliCompactCapable?: boolean
  /** #516: the seat passes the swarm-owned plugins gate (#511's predicate). */
  pluginsSwarmOwned?: boolean
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
  'Compact summarises server-side history — CLI and remote seats keep their transcript in the provider'

/** #636: what a greyed CLI Compact says — the gate is the missing API. */
export const COMPACT_NO_API_REASON =
  'No API is configured — compacting a CLI seat needs a default API profile (Settings → LLM)'

export const COMPACT_REMOTE_REASON =
  'Compact is not available for remote seats — the transcript belongs to the remote provider'

/** #516: Plugins ride the swarm-owned reading of #511 (API + blueprint seats) —
 * the same predicate the rail's Plugins entry and the badge gate on. */
export const PLUGINS_DISABLED_REASON =
  'Plugins are available on API and blueprint seats — CLI and remote seats run their tools on the provider'

export function composerMenuCapabilities(seat: ComposerMenuSeat): ComposerMenuCapabilities {
  // One owner for the attach rule: the same helper the composer uses to decide
  // whether the paperclip is live, so the menu cannot disagree with the input.
  const addFiles = composerFileAttachSupported({
    isCli: seat.isCli,
    isRemote: seat.isRemote,
  })
  // Compact is API-only. `isApi` is the deliberate gate rather than
  // `!isCli && !isRemote`, because a seat that is none of the three (an
  // unresolved blueprint, say) must not silently gain the action.
  const compact = Boolean(seat.isApi)
  // #636: a CLI seat can compact too — the server summarises via the default
  // API, or the provider compacts itself through its declared native hook.
  // Remote seats stay out: their transcript is the provider's, and the server
  // has no summariser for it.
  const cliCompact =
    Boolean(seat.isCli) && (Boolean(seat.defaultLlmReady) || Boolean(seat.cliCompactCapable))
  const compactReason = seat.isRemote
    ? COMPACT_REMOTE_REASON
    : COMPACT_NO_API_REASON
  // #516: the Plugins entry uses the same swarm-owned reading (#511) the rail
  // footer and the badge already gate on — one predicate, three consumers.
  const plugins = Boolean(seat.pluginsSwarmOwned)
  return {
    addFiles: { enabled: addFiles, reason: ATTACH_DISABLED_REASON },
    compact: {
      enabled: compact || cliCompact,
      reason: compact || cliCompact ? '' : compactReason,
    },
    plugins: { enabled: plugins, reason: PLUGINS_DISABLED_REASON },
  }
}
