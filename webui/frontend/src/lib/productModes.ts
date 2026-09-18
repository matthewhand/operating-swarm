/**
 * CLI-first product modes (#151 / #149).
 *
 * Shipped default: CLI on; API / Blueprint / Team / Remote off until Settings
 * enables them. Disabled modes stay out of the default rail/navbar.
 *
 * `GET /v1/cli-agents/` always advertises `modes`. Payloads without `modes`
 * (legacy tests / older servers) keep every surface visible.
 */

export const PRODUCT_MODE_KEYS = ['cli', 'api', 'blueprint', 'team', 'remote'] as const

export type ProductMode = (typeof PRODUCT_MODE_KEYS)[number]

export type ProductModes = Record<ProductMode, boolean>

export const DEFAULT_PRODUCT_MODES: ProductModes = {
  cli: true,
  api: false,
  blueprint: false,
  team: false,
  remote: false,
}

/** Legacy / missing payload: do not hide surfaces the API has not advertised. */
export const LEGACY_ALL_ON_PRODUCT_MODES: ProductModes = {
  cli: true,
  api: true,
  blueprint: true,
  team: true,
  remote: true,
}

export const PRODUCT_MODE_LABELS: Record<ProductMode, string> = {
  cli: 'CLI',
  api: 'API',
  blueprint: 'Blueprint',
  team: 'Team',
  remote: 'Remote',
}

export const PRODUCT_MODE_LIMITATIONS: Record<ProductMode, string> = {
  cli: 'On: rail and navbar list discovered host CLIs only. Known catalog names that are not on PATH stay absent. Off: no CLI rail seat or Manage CLI footer.',
  api: 'On: api_agent rail seat and Manage API navbar footer (LiteLLM profiles). Off: API seats stay out of the default rail/navbar.',
  blueprint: 'On: blueprint rail seats and Manage Blueprint. Off: blueprint catalog seats stay off the default rail/navbar.',
  team: 'On: team rail rows and Manage Team. Off: teams stay out of the default rail/navbar.',
  remote: 'On: remote rail rows and Manage Remote. Off: remotes stay out of the default rail/navbar.',
}

export function resolveProductModes(
  payload?: { modes?: Partial<ProductModes> | null } | null,
): ProductModes {
  if (!payload || payload.modes == null) {
    return { ...LEGACY_ALL_ON_PRODUCT_MODES }
  }
  const raw = payload.modes
  return {
    cli: raw.cli ?? DEFAULT_PRODUCT_MODES.cli,
    api: raw.api ?? DEFAULT_PRODUCT_MODES.api,
    blueprint: raw.blueprint ?? DEFAULT_PRODUCT_MODES.blueprint,
    team: raw.team ?? DEFAULT_PRODUCT_MODES.team,
    remote: raw.remote ?? DEFAULT_PRODUCT_MODES.remote,
  }
}

export function isProductModeEnabled(modes: ProductModes, key: ProductMode): boolean {
  return modes[key] === true
}

/**
 * #594: the mode set to use while the fetch may still be in flight.
 *
 * `resolveProductModes` treats a missing payload as *"a legacy server that
 * advertises nothing"* and turns every surface on. That is correct for a legacy
 * server, but `cliQuery` has no `initialData`, so the **first paint of every page
 * load on a modern server** was also `undefined` — and the rail painted CLI +
 * API + blueprint + team + remote rows before dropping the gated ones a moment
 * later when the real modes arrived. A rail that loses half its rows one second
 * in reads as breakage.
 *
 * So the two situations are separated here:
 *
 * | State | Result |
 * |---|---|
 * | in flight (`settled: false`) | shipped defaults — CLI only, the **narrowest** rail |
 * | settled, fetch **failed** | legacy all-on — never hide a surface we could not verify |
 * | settled, payload present | `resolveProductModes` (unchanged legacy contract) |
 *
 * Starting narrow and growing is the point: a rail that gains rows is legible,
 * a rail that loses them is not.
 */
export function productModesWhenSettled({
  data,
  settled,
  failed = false,
}: {
  data?: { modes?: Partial<ProductModes> | null } | null
  /** Whether the fetch has resolved (success **or** error). */
  settled: boolean
  /** The fetch itself errored. */
  failed?: boolean
}): ProductModes {
  if (!settled) return { ...DEFAULT_PRODUCT_MODES }
  if (failed) return { ...LEGACY_ALL_ON_PRODUCT_MODES }
  return resolveProductModes(data)
}
