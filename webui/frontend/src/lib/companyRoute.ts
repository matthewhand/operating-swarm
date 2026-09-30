/**
 * #1317 — Company model auto-route for the composer.
 *
 * The route fills an empty model pick. An explicit picker value wins.
 * The patch never carries a seat id or ``blueprint_id``.
 */
import { fetchWithAuth } from './api/client'

export interface CompanyRoute {
  applied: boolean
  model: string
  provider: string
  source: string
  company_id?: string
  company_slug?: string
  requested_model?: string
  reason?: string
}

export const EMPTY_COMPANY_ROUTE: CompanyRoute = {
  applied: false,
  model: '',
  provider: '',
  source: 'none',
}

export async function fetchCompanyRoute(): Promise<CompanyRoute> {
  try {
    const response = await fetchWithAuth('/v1/company-route/')
    if (!response.ok) return EMPTY_COMPANY_ROUTE
    const data = (await response.json()) as Partial<CompanyRoute>
    return {
      applied: Boolean(data.applied),
      model: String(data.model || ''),
      provider: String(data.provider || ''),
      source: String(data.source || 'none'),
      company_id: data.company_id,
      company_slug: data.company_slug,
      requested_model: data.requested_model,
      reason: data.reason,
    }
  } catch {
    return EMPTY_COMPANY_ROUTE
  }
}

/** Explicit picker value wins. Otherwise the auto-applied Company model. */
export function modelForCompanyRoute(
  explicitModel: string,
  route: { applied?: boolean; model?: string } | null | undefined,
): string {
  const explicit = (explicitModel || '').trim()
  if (explicit && explicit !== 'default') return explicit
  const auto = (route?.applied && route.model ? route.model : '').trim()
  return auto || explicit
}

/**
 * Routing params for a turn. Keys are only ``model`` when one is selected.
 * Callers keep the active blueprint id themselves.
 */
export function routingPatchForCompanyRoute(
  explicitModel: string,
  route: { applied?: boolean; model?: string } | null | undefined,
): { model?: string } {
  const model = modelForCompanyRoute(explicitModel, route)
  if (!model || model === 'default') return {}
  return { model }
}
