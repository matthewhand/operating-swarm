import type { Blueprint } from './api'
import { exampleRoleAgents } from './agentRoles'

/**
 * REQ-170 / REQ-171B: a catalog recipe is a rail seat only when the API sets
 * `rail: true`. Missing / false = Settings / Add-agent catalog only. CLI /
 * Herdr / named API kind rows from other endpoints stay seats. Add-agent
 * CLI/API creates persist `rail: true` so `GET /v1/blueprints/` can list them.
 */
export function isRailSeat(row: {
  rail?: boolean | null
  kind?: string | null
}): boolean {
  const kind = String(row.kind || '').trim().toLowerCase()
  if (kind === 'cli' || kind === 'herdr' || kind === 'api' || kind === 'blueprint') return true
  return row.rail === true
}

/** Discovery catalog rows that may appear on the AGENTS rail. Default deny. */
export function isCatalogRailSeat(row: { rail?: boolean | null }): boolean {
  return row.rail === true
}

/** Inject example roles after dropping catalog-only recipes. */
export function railSeatAgents(catalog: Blueprint[]): Blueprint[] {
  return exampleRoleAgents(catalog.filter(isCatalogRailSeat))
}

/**
 * Editor rule (REQ-170): when the seat display name equals the assigned
 * blueprint id or name, the labeled "Blueprint" heading is redundant.
 */
export function displayNameMatchesBlueprint(
  displayName: string,
  blueprintId: string,
  blueprintName?: string | null,
): boolean {
  const name = displayName.trim().toLowerCase()
  if (!name) return false
  if (name === blueprintId.trim().toLowerCase()) return true
  const recipe = (blueprintName || '').trim().toLowerCase()
  return Boolean(recipe) && name === recipe
}

/** Pin / team / remote / herdr ids that are not catalog recipes. */
export function isNonCatalogRailPinId(id: string): boolean {
  return (
    id.startsWith('team:') ||
    id.startsWith('remote:') ||
    id.startsWith('herdr:')
  )
}
