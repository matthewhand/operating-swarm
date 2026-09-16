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
