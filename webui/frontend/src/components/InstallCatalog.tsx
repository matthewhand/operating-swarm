import { useCallback, useEffect, useMemo, useState } from 'react'
import { ExternalLink, Plug, Search, Settings2, Star, Trash2, X } from 'lucide-react'
import { Badge, Button, LoadingSpinner } from './DaisyUI'
import {
  deleteMcpPlugin,
  discoverMcpPluginTools,
  fetchMarketplaceCatalog,
  fetchMcpPlugins,
  installMarketplaceItem,
  previewMarketplaceItem,
  upsertMcpPlugin,
} from '../lib/api'
import {
  COMMUNITY_DANGER,
  SKILLS_CATALOG_EMPTY_BODY,
  SKILLS_CATALOG_EMPTY_TITLE,
  filterCatalogItems,
  installAndProbe,
  mergeCatalog,
  usesBackendInstall,
  type CatalogKindFilter,
  type CatalogSurface,
  type HealthDot,
  type InstallCatalogItem,
  type InstallOutcome,
  type InstallStatus,
} from '../lib/installCatalog'
import { serversFromApi } from '../lib/mcpServers'

const TOOL_FILTERS: { id: CatalogKindFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'local', label: 'Local' },
  { id: 'remote', label: 'Remote' },
  { id: 'community', label: 'Community' },
  { id: 'installed', label: 'Installed' },
]

const SKILL_FILTERS: { id: CatalogKindFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'community', label: 'Community' },
  { id: 'installed', label: 'Installed' },
]

const TEAM_FILTERS: { id: CatalogKindFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'community', label: 'Community' },
  { id: 'installed', label: 'Installed' },
]

function filtersFor(surface: CatalogSurface) {
  if (surface === 'skills') return SKILL_FILTERS
  if (surface === 'teams') return TEAM_FILTERS
  return TOOL_FILTERS
}

function catalogKind(surface: CatalogSurface): 'plugins' | 'skills' | 'teams' {
  if (surface === 'skills') return 'skills'
  if (surface === 'teams') return 'teams'
  return 'plugins'
}

export interface InstallCatalogProps {
  surface: CatalogSurface
  items?: InstallCatalogItem[]
  warnings?: string[]
  autoLoad?: boolean
  onInstall?: (item: InstallCatalogItem) => Promise<InstallOutcome>
  onRemove?: (item: InstallCatalogItem) => Promise<void>
  onManage?: (item: InstallCatalogItem) => void
}

function healthLabel(health: HealthDot): string {
  if (health === 'up') return 'Connected'
  if (health === 'down') return 'Unreachable'
  return 'Not checked'
}

function HealthMark({ health, name }: { health: HealthDot; name: string }) {
  return (
    <span
      className={`os-health-dot os-health-dot--${health}`}
      data-testid="os-health-dot"
      data-health={health}
      aria-label={`${name} ${healthLabel(health)}`}
      title={healthLabel(health)}
    />
  )
}

export default function InstallCatalog({
  surface,
  items: itemsProp,
  warnings: warningsProp,
  autoLoad = true,
  onInstall,
  onRemove,
  onManage,
}: InstallCatalogProps) {
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState<CatalogKindFilter>('all')
  const [loaded, setLoaded] = useState<InstallCatalogItem[]>(itemsProp || [])
  const [warnings, setWarnings] = useState<string[]>(warningsProp || [])
  const [loading, setLoading] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [installStates, setInstallStates] = useState<Record<string, InstallStatus>>({})
  const [healthById, setHealthById] = useState<Record<string, HealthDot>>({})
  const [messages, setMessages] = useState<Record<string, string>>({})
  const [previewNotes, setPreviewNotes] = useState<string[]>([])

  useEffect(() => {
    if (itemsProp) setLoaded(itemsProp)
  }, [itemsProp])

  useEffect(() => {
    if (warningsProp) setWarnings(warningsProp)
  }, [warningsProp])

  useEffect(() => {
    if (!autoLoad || itemsProp) return
    let cancelled = false
    setLoading(true)
    void (async () => {
      const scanWarnings: string[] = []
      let backend = null
      try {
        backend = await fetchMarketplaceCatalog(catalogKind(surface))
      } catch (err) {
        scanWarnings.push(err instanceof Error ? err.message : 'Marketplace catalog failed.')
      }
      let installed = [] as ReturnType<typeof serversFromApi>
      if (surface === 'tools') {
        try {
          installed = serversFromApi(await fetchMcpPlugins())
        } catch {
          scanWarnings.push('Could not load installed MCP servers.')
        }
      }
      if (cancelled) return
      const merged = mergeCatalog({
        backend,
        installed,
        includeTemplates: surface === 'tools',
      })
      setLoaded(merged.items)
      setWarnings([...scanWarnings, ...merged.warnings])
      setLoading(false)
    })()
    return () => {
      cancelled = true
    }
  }, [autoLoad, itemsProp, surface])

  const visible = useMemo(
    () => filterCatalogItems(loaded, query, kind),
    [kind, loaded, query],
  )
  const selected = visible.find((item) => item.id === selectedId) || loaded.find((item) => item.id === selectedId) || null

  const runInstall = useCallback(
    async (item: InstallCatalogItem) => {
      setInstallStates((prev) => ({ ...prev, [item.id]: 'installing' }))
      setMessages((prev) => ({ ...prev, [item.id]: 'Installing…' }))
      const runner =
        onInstall ||
        ((next) =>
          installAndProbe(next, {
            upsert: upsertMcpPlugin,
            discover: discoverMcpPluginTools,
            install: installMarketplaceItem,
          }))
      try {
        const outcome = await runner(item)
        setInstallStates((prev) => ({ ...prev, [item.id]: outcome.status }))
        setHealthById((prev) => ({ ...prev, [item.id]: outcome.health }))
        setMessages((prev) => ({ ...prev, [item.id]: outcome.message }))
        if (outcome.status === 'ok') {
          setLoaded((prev) =>
            prev.map((row) => (row.id === item.id ? { ...row, installed: true } : row)),
          )
        }
      } catch (err) {
        setInstallStates((prev) => ({ ...prev, [item.id]: 'fail' }))
        setMessages((prev) => ({
          ...prev,
          [item.id]: err instanceof Error ? err.message : 'Install failed.',
        }))
      }
    },
    [onInstall],
  )

  const runRemove = useCallback(
    async (item: InstallCatalogItem) => {
      setInstallStates((prev) => ({ ...prev, [item.id]: 'installing' }))
      try {
        if (onRemove) await onRemove(item)
        else await deleteMcpPlugin(item.id)
        setLoaded((prev) =>
          prev.map((row) => (row.id === item.id ? { ...row, installed: false } : row)),
        )
        setInstallStates((prev) => ({ ...prev, [item.id]: 'idle' }))
        setHealthById((prev) => ({ ...prev, [item.id]: 'unknown' }))
        setMessages((prev) => ({ ...prev, [item.id]: 'Removed.' }))
      } catch (err) {
        setInstallStates((prev) => ({ ...prev, [item.id]: 'fail' }))
        setMessages((prev) => ({
          ...prev,
          [item.id]: err instanceof Error ? err.message : 'Remove failed.',
        }))
      }
    },
    [onRemove],
  )

  useEffect(() => {
    if (!selected || !usesBackendInstall(selected) || selected.kind !== 'team') {
      setPreviewNotes([])
      return
    }
    if ((selected.members || []).length > 0) {
      setPreviewNotes([])
      return
    }
    let cancelled = false
    void previewMarketplaceItem('teams', selected.id)
      .then((payload) => {
        if (cancelled) return
        const roster = (payload.roster || {}) as {
          members?: InstallCatalogItem['members']
          wires?: InstallCatalogItem['wires']
          chief_of_staff_id?: string | null
          needs_configuration?: InstallCatalogItem['needsConfiguration']
        }
        setLoaded((prev) =>
          prev.map((row) =>
            row.id === selected.id
              ? {
                  ...row,
                  members: roster.members,
                  wires: roster.wires,
                  chiefOfStaffId: roster.chief_of_staff_id ?? null,
                  needsConfiguration: roster.needs_configuration,
                }
              : row,
          ),
        )
        setPreviewNotes([])
      })
      .catch((err) => {
        if (!cancelled) {
          setPreviewNotes([err instanceof Error ? err.message : 'Preview failed.'])
        }
      })
    return () => {
      cancelled = true
    }
  }, [selected?.id, selected?.kind])

  const emptySkills = surface === 'skills' && loaded.length === 0
  const emptyFilter = !emptySkills && !loading && visible.length === 0
  const kindFilters = filtersFor(surface)

  return (
    <section
      className="os-install-catalog"
      data-testid="os-install-catalog"
      data-surface={surface}
    >
      <div className="os-install-catalog__search">
        <Search className="h-4 w-4 shrink-0 text-base-content/45" aria-hidden="true" />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search catalog"
          aria-label="Search catalog"
          data-testid="os-install-search"
          className="os-search-palette__input"
          autoComplete="off"
        />
      </div>
      <div
        className="os-install-kind-filters join"
        role="toolbar"
        aria-label="Kind filters"
        data-testid="os-install-kind-filters"
      >
        {kindFilters.map((filter) => (
          <button
            key={filter.id}
            type="button"
            className={`btn btn-xs join-item ${kind === filter.id ? 'btn-primary' : 'btn-ghost'}`}
            aria-pressed={kind === filter.id}
            onClick={() => setKind(filter.id)}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {warnings.map((warning) => (
        <p key={warning} className="px-4 text-xs text-warning" role="status">
          {warning}
        </p>
      ))}

      {loading ? (
        <div className="flex items-center gap-2 px-4 py-3 text-xs text-base-content/60">
          <LoadingSpinner size="sm" aria-label="Loading catalog" />
          Loading catalog…
        </div>
      ) : null}

      <div className="os-install-catalog__body">
        <ul
          className="os-install-cards"
          role="list"
          aria-label={
            surface === 'skills' ? 'Skill packs' : surface === 'teams' ? 'Team packs' : 'Tool catalog'
          }
        >
          {emptySkills ? (
            <li className="os-search-empty" data-testid="os-install-empty">
              <p className="font-medium">{SKILLS_CATALOG_EMPTY_TITLE}</p>
              <p className="mt-1 text-xs text-base-content/60">{SKILLS_CATALOG_EMPTY_BODY}</p>
            </li>
          ) : emptyFilter ? (
            <li className="os-search-empty" data-testid="os-install-empty">
              {query.trim()
                ? `No matches for “${query.trim()}”.`
                : 'Nothing in this filter right now.'}
            </li>
          ) : (
            visible.map((item) => {
              const status = installStates[item.id] || 'idle'
              const health = healthById[item.id] || (item.installed ? 'unknown' : 'unknown')
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    className={`os-install-card card card-sm card-border bg-base-200 w-full text-left ${
                      selectedId === item.id ? 'os-install-card--active' : ''
                    }`}
                    data-testid="os-install-card"
                    data-item-id={item.id}
                    data-installed={item.installed ? 'true' : 'false'}
                    data-kind={item.kind}
                    data-status={status}
                    onClick={() => setSelectedId(item.id)}
                  >
                    <span className="os-install-card__icon" aria-hidden="true">
                      <Plug className="h-4 w-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="os-install-card__name">{item.name}</span>
                      <span className="os-install-card__summary">{item.summary}</span>
                      <span className="os-install-card__meta">
                        <Badge size="sm" outline>
                          {item.sourceLabel}
                        </Badge>
                        {typeof item.stars === 'number' ? (
                          <span className="inline-flex items-center gap-0.5 text-[11px] text-base-content/55">
                            <Star className="h-3 w-3" aria-hidden="true" />
                            {item.stars}
                          </span>
                        ) : null}
                        {typeof item.installs === 'number' ? (
                          <span className="text-[11px] text-base-content/55">{item.installs} installs</span>
                        ) : null}
                      </span>
                    </span>
                    {item.installed ? (
                      <span className="flex items-center gap-1">
                        <HealthMark health={health} name={item.name} />
                        <Badge type="success" size="sm">
                          Installed
                        </Badge>
                      </span>
                    ) : null}
                  </button>
                </li>
              )
            })
          )}
        </ul>

        {selected ? (
          <aside
            className="os-install-drawer"
            data-testid="os-install-drawer"
            aria-label={`${selected.name} details`}
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <h3 className="text-sm font-semibold">{selected.name}</h3>
                <p className="text-xs text-base-content/60">{selected.summary}</p>
              </div>
              <button
                type="button"
                className="btn btn-ghost btn-xs btn-circle"
                aria-label="Close details"
                onClick={() => setSelectedId(null)}
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <p className="mt-2 text-xs">
              Source: {selected.sourceLabel}
              {selected.external ? ` · ${COMMUNITY_DANGER}` : ''}
            </p>
            {typeof selected.stars === 'number' ? (
              <p className="text-xs text-base-content/60">{selected.stars} stars</p>
            ) : null}
            <div className="mt-2">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-base-content/45">
                Required env
              </p>
              {selected.requiredEnv.length === 0 ? (
                <p className="text-xs text-base-content/60">None declared.</p>
              ) : (
                <ul className="text-xs font-mono" aria-label="Required env vars">
                  {selected.requiredEnv.map((name) => (
                    <li key={name}>{name}</li>
                  ))}
                </ul>
              )}
            </div>
            <div className="mt-2">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-base-content/45">
                Tools provided
              </p>
              {selected.toolsProvided.length === 0 ? (
                <p className="text-xs text-base-content/60">None in this payload.</p>
              ) : (
                <ul className="text-xs font-mono" aria-label="Tools provided">
                  {selected.toolsProvided.map((name) => (
                    <li key={name}>{name}</li>
                  ))}
                </ul>
              )}
            </div>
            {selected.kind === 'team' ? (
              <div className="mt-2" data-testid="os-install-team-preview">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-base-content/45">
                  Roster preview
                </p>
                {previewNotes.map((note) => (
                  <p key={note} className="text-xs text-warning" role="status">
                    {note}
                  </p>
                ))}
                {selected.chiefOfStaffId ? (
                  <p className="text-xs">Chief of Staff: {selected.chiefOfStaffId}</p>
                ) : (
                  <p className="text-xs text-base-content/60">No Chief of Staff in this pack.</p>
                )}
                {selected.wires ? (
                  <p className="text-xs">
                    Wires: handoff {selected.wires.handoff ? 'on' : 'off'}, as_tool{' '}
                    {selected.wires.as_tool ? 'on' : 'off'}
                  </p>
                ) : null}
                {(selected.members || []).length === 0 ? (
                  <p className="text-xs text-base-content/60">Open the pack to load members before install.</p>
                ) : (
                  <ul className="text-xs" aria-label="Team members">
                    {(selected.members || []).map((member) => (
                      <li key={member.id}>
                        {member.name || member.id} ({member.kind}
                        {member.role ? ` · ${member.role}` : ''})
                      </li>
                    ))}
                  </ul>
                )}
                {(selected.needsConfiguration || []).length > 0 ? (
                  <ul className="mt-1 text-xs text-warning" aria-label="Needs configuration">
                    {(selected.needsConfiguration || []).map((row) => (
                      <li key={row.id}>{row.reason}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
            {selected.dangerNotes.length > 0 ? (
              <div className="mt-2">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-warning">
                  Notes
                </p>
                <ul className="text-xs text-warning">
                  {selected.dangerNotes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {selected.htmlUrl ? (
              <a
                className="link mt-2 inline-flex items-center gap-1 text-xs"
                href={selected.htmlUrl}
                target="_blank"
                rel="noreferrer noopener"
              >
                Open on GitHub
                <ExternalLink className="h-3 w-3" aria-hidden="true" />
              </a>
            ) : null}

            {(() => {
              const status = installStates[selected.id] || 'idle'
              const health = healthById[selected.id] || 'unknown'
              const message = messages[selected.id]
              return (
                <div className="mt-3 space-y-2">
                  {status === 'installing' ? (
                    <progress className="progress progress-primary w-full" aria-label="Install progress" />
                  ) : null}
                  <p
                    className="text-xs"
                    data-testid="os-install-status"
                    data-status={status}
                    role="status"
                  >
                    {message || status}
                  </p>
                  {selected.installed ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <HealthMark health={health} name={selected.name} />
                      <Button
                        type="button"
                        size="xs"
                        variant="ghost"
                        data-testid="os-manage-btn"
                        onClick={() => onManage?.(selected)}
                      >
                        <Settings2 className="h-3.5 w-3.5" aria-hidden="true" />
                        Manage
                      </Button>
                      <Button
                        type="button"
                        size="xs"
                        variant="ghost"
                        data-testid="os-remove-btn"
                        onClick={() => void runRemove(selected)}
                        disabled={status === 'installing'}
                      >
                        <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                        Remove
                      </Button>
                    </div>
                  ) : (
                    <Button
                      type="button"
                      size="sm"
                      variant="primary"
                      data-testid="os-install-btn"
                      disabled={!selected.installable || status === 'installing'}
                      loading={status === 'installing'}
                      onClick={() => void runInstall(selected)}
                    >
                      Install
                    </Button>
                  )}
                  {!selected.installable && !selected.installed && selected.installHint ? (
                    <p className="text-xs text-base-content/60">{selected.installHint}</p>
                  ) : null}
                </div>
              )
            })()}
          </aside>
        ) : null}
      </div>
    </section>
  )
}
