/** #856 slice A — marketplace endpoints (moved verbatim from lib/api.ts). */
import {
  apiGet,
  apiPost,
} from './client'
import type {
  MarketplaceCatalogKind,
  MarketplaceCatalogResponse,
  MarketplaceInstallResponse,
} from './types'

export function fetchMarketplaceCatalog(
  kind: MarketplaceCatalogKind,
): Promise<MarketplaceCatalogResponse> {
  return apiGet<MarketplaceCatalogResponse>(`/v1/marketplace/catalog/?kind=${kind}`)
}
export function previewMarketplaceItem(
  kind: MarketplaceCatalogKind,
  id: string,
): Promise<Record<string, unknown>> {
  return apiGet<Record<string, unknown>>(
    `/v1/marketplace/preview/?kind=${kind}&id=${encodeURIComponent(id)}`,
  )
}
export function installMarketplaceItem(
  kind: MarketplaceCatalogKind,
  id: string,
): Promise<MarketplaceInstallResponse> {
  return apiPost<MarketplaceInstallResponse>('/v1/marketplace/install/', { kind, id })
}
