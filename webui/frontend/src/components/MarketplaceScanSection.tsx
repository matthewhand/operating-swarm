import { useCallback, useEffect, useState } from 'react'
import { ExternalLink, Globe } from 'lucide-react'
import { apiGet } from '../lib/api'

/** #179 — community GitHub scan results, shared by Teams + Plugins popups. */

export interface MarketplaceItem {
  id: string
  name: string
  full_name: string
  owner: string
  description: string
  html_url: string
  stars: number
  topics: string[]
  updated_at: string
}

export interface MarketplaceScanResponse {
  object: 'marketplace_scan'
  kind: 'teams' | 'plugins'
  topics: string[]
  external: true
  items: MarketplaceItem[]
  warnings: string[]
}

export type MarketplaceKind = 'teams' | 'plugins'

export function fetchMarketplaceScan(kind: MarketplaceKind): Promise<MarketplaceScanResponse> {
  return apiGet<MarketplaceScanResponse>(`/v1/marketplace/?kind=${kind}`)
}

/**
 * Collapsible "Get more from GitHub" section. Renders community scan
 * results with an external-content label and an honest empty state.
 */
export function MarketplaceScanSection({ kind }: { kind: MarketplaceKind }) {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState<MarketplaceScanResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const runScan = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setData(await fetchMarketplaceScan(kind))
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Scan failed.')
    } finally {
      setLoading(false)
    }
  }, [kind])

  useEffect(() => {
    if (open && !data && !loading && !error) {
      void runScan()
    }
  }, [open, data, loading, error, runScan])

  return (
    <section className="os-marketplace" data-testid="marketplace-section" data-kind={kind}>
      <button
        type="button"
        className="btn btn-ghost btn-xs text-primary"
        data-testid="marketplace-toggle"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <Globe className="h-3.5 w-3.5" aria-hidden="true" />
        Get more from GitHub
      </button>
      {open && (
        <div className="os-marketplace__results" data-testid="marketplace-results">
          <p className="os-marketplace__label text-xs text-base-content/60">
            Community / external content — not vetted by open-swarm.
          </p>
          {loading && <p className="text-xs">Scanning GitHub…</p>}
          {error && <p className="text-xs text-error">{error}</p>}
          {!loading && !error && data && (
            <>
              {data.warnings.map((warning) => (
                <p key={warning} className="text-xs text-warning" role="status">
                  {warning}
                </p>
              ))}
              {data.items.length === 0 ? (
                <p className="text-xs text-base-content/60">
                  Nothing found for these tags right now.
                </p>
              ) : (
                <ul className="os-marketplace__list" role="list">
                  {data.items.map((item) => (
                    <li key={item.id} className="os-marketplace__item" data-testid="marketplace-item">
                      <a
                        className="link text-sm font-medium"
                        href={item.html_url}
                        target="_blank"
                        rel="noreferrer noopener"
                      >
                        {item.full_name}
                        <ExternalLink className="ml-1 inline h-3 w-3" aria-hidden="true" />
                      </a>
                      {item.description && (
                        <span className="block text-xs text-base-content/60">{item.description}</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      )}
    </section>
  )
}
