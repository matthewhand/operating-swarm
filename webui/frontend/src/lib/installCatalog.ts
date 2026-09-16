/**
 * REQ-858 / #213 — catalog rows for the Add tools / Add skills popups.
 *
 * Phase 1 derives cards from shipped MCP templates, GitHub marketplace
 * scan, and /v1/mcp-plugins/. No new backend. Env values never leave
 * this module as display text — keys only.
 */

import {
  MCP_SERVER_TEMPLATES,
  entryToUpsertBody,
  newMcpServerId,
  type McpServerEntry,
} from './mcpServers'
import type { MarketplaceItem, MarketplaceScanResponse } from '../components/MarketplaceScanSection'
import type { McpPluginDiscoverPayload, McpPluginsPayload } from './api'

export type CatalogSurface = 'tools' | 'skills'
export type CatalogKindFilter = 'all' | 'local' | 'remote' | 'community' | 'installed' | 'shipped'
export type CatalogSourceKind = 'shipped' | 'github' | 'installed'
export type CatalogItemKind = 'local' | 'remote' | 'openapi' | 'community' | 'skill'
export type InstallStatus = 'idle' | 'installing' | 'ok' | 'fail'
export type HealthDot = 'up' | 'down' | 'unknown'

const ENV_NAME_RE = /^[A-Z][A-Z0-9_]*$/
const SECRETISH_RE = /sk-|api[_-]?key|bearer\s|password|secret/i
const GITHUB_REPO_RE = /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/i

export const SKILLS_CATALOG_EMPTY_TITLE = 'No skill packs to install yet'
export const SKILLS_CATALOG_EMPTY_BODY =
  'A skill-pack catalog has not landed on the server. Bundled skills stay in the composer — this list is empty on purpose, not a failed scan.'

export const COMMUNITY_DANGER =
  'Community / external content — not vetted by open-swarm.'

export const COMMUNITY_INSTALL_HINT =
  'GitHub scan has no MCP command or URL. Open the repo, or add it in Manage.'

export interface InstallCatalogItem {
  id: string
  name: string
  summary: string
  sourceLabel: string
  sourceKind: CatalogSourceKind
  kind: CatalogItemKind
  stars?: number
  installs?: number
  requiredEnv: string[]
  toolsProvided: string[]
  dangerNotes: string[]
  htmlUrl?: string
  topics?: string[]
  external: boolean
  installable: boolean
  installHint?: string
  installed: boolean
  command?: string
  args?: string[]
  url?: string
  openapiSpecUrl?: string
  note?: string
}

export interface InstallOutcome {
  status: Exclude<InstallStatus, 'idle' | 'installing'>
  health: HealthDot
  message: string
}

export interface CatalogLoad {
  items: InstallCatalogItem[]
  warnings: string[]
}

export function envNamesOnly(env: Record<string, string> | undefined | null): string[] {
  if (!env || typeof env !== 'object') return []
  const names = Object.keys(env)
    .map((key) => key.trim())
    .filter((key) => ENV_NAME_RE.test(key))
  names.sort()
  return names
}

/** Drop secret-shaped copy; React still text-escapes whatever remains. */
export function catalogText(value: unknown, max = 160): string {
  const raw = String(value ?? '')
    .replace(/\s+/g, ' ')
    .trim()
  if (!raw || SECRETISH_RE.test(raw)) return ''
  return raw.length > max ? `${raw.slice(0, max - 1)}…` : raw
}

export function safeGithubUrl(raw: unknown): string | undefined {
  if (typeof raw !== 'string') return undefined
  const trimmed = raw.trim().split(/[?#]/)[0]
  if (!GITHUB_REPO_RE.test(trimmed)) return undefined
  return trimmed.replace(/\/$/, '')
}

export function matchesQuery(item: InstallCatalogItem, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  const hay = [
    item.name,
    item.summary,
    item.sourceLabel,
    item.kind,
    ...(item.toolsProvided || []),
    ...(item.topics || []),
  ]
    .join(' ')
    .toLowerCase()
  return hay.includes(needle)
}

export function matchesKind(item: InstallCatalogItem, kind: CatalogKindFilter): boolean {
  if (kind === 'all') return true
  if (kind === 'installed') return item.installed
  if (kind === 'shipped') return item.sourceKind === 'shipped'
  if (kind === 'community') return item.sourceKind === 'github' || item.kind === 'community'
  if (kind === 'local') return item.kind === 'local'
  if (kind === 'remote') return item.kind === 'remote'
  return true
}

export function filterCatalogItems(
  items: readonly InstallCatalogItem[],
  query: string,
  kind: CatalogKindFilter,
): InstallCatalogItem[] {
  return items.filter((item) => matchesKind(item, kind) && matchesQuery(item, query))
}

function templateDanger(note: string): string[] {
  if (/scoped|filesystem|write_file|danger/i.test(note)) return [note]
  return []
}

export function templateToCatalogItem(
  template: (typeof MCP_SERVER_TEMPLATES)[number],
  installedIds: ReadonlySet<string>,
): InstallCatalogItem {
  const id = newMcpServerId(template.name)
  const note = catalogText(template.note || '')
  return {
    id,
    name: template.name,
    summary: note || 'Shipped MCP server.',
    sourceLabel: 'Shipped',
    sourceKind: 'shipped',
    kind: template.kind === 'remote' ? 'remote' : 'local',
    requiredEnv: envNamesOnly(template.env),
    toolsProvided: [...(template.provides || [])],
    dangerNotes: templateDanger(note),
    external: false,
    installable: Boolean(template.command || template.url),
    installHint: template.command || template.url ? undefined : 'Template is missing a command.',
    installed: installedIds.has(id),
    command: template.command,
    args: template.args ? [...template.args] : [],
    url: template.url,
    note,
  }
}

export function marketplaceToCatalogItem(row: MarketplaceItem): InstallCatalogItem {
  const id = catalogText(row.id || row.full_name || row.name, 80) || 'github-item'
  const stars = typeof row.stars === 'number' && row.stars >= 0 ? row.stars : undefined
  const installs =
    typeof (row as { installs?: unknown }).installs === 'number' &&
    (row as { installs: number }).installs >= 0
      ? (row as { installs: number }).installs
      : undefined
  return {
    id,
    name: catalogText(row.name || row.full_name, 80) || id,
    summary: catalogText(row.description) || 'No description in the scan payload.',
    sourceLabel: 'GitHub',
    sourceKind: 'github',
    kind: 'community',
    stars,
    installs,
    requiredEnv: [],
    toolsProvided: [],
    dangerNotes: [COMMUNITY_DANGER],
    htmlUrl: safeGithubUrl(row.html_url),
    topics: Array.isArray(row.topics) ? row.topics.map((topic) => catalogText(topic, 40)).filter(Boolean) : [],
    external: true,
    installable: false,
    installHint: COMMUNITY_INSTALL_HINT,
    installed: false,
  }
}

export function installedToCatalogItem(server: McpServerEntry): InstallCatalogItem {
  const kind: CatalogItemKind =
    server.source === 'openapi' ? 'openapi' : server.kind === 'remote' ? 'remote' : 'local'
  const summary =
    catalogText(server.note) ||
    (server.kind === 'remote' ? catalogText(server.url, 80) : [server.command, ...(server.args || [])].filter(Boolean).join(' '))
  return {
    id: server.id,
    name: server.name || server.id,
    summary: summary || 'Configured MCP server.',
    sourceLabel: 'Installed',
    sourceKind: 'installed',
    kind,
    requiredEnv: envNamesOnly(server.env),
    toolsProvided: server.tools.length
      ? server.tools.map((tool) => tool.name)
      : [...(server.provides || [])],
    dangerNotes: templateDanger(server.note || ''),
    external: false,
    installable: false,
    installHint: 'Already installed.',
    installed: true,
    command: server.command,
    args: server.args,
    url: server.url,
    openapiSpecUrl: server.openapi_spec_url,
    note: catalogText(server.note),
  }
}

export function mergeCatalog(args: {
  templates?: readonly (typeof MCP_SERVER_TEMPLATES)[number][]
  marketplace?: MarketplaceScanResponse | null
  installed?: readonly McpServerEntry[]
}): CatalogLoad {
  const installed = args.installed || []
  const installedIds = new Set(installed.map((row) => row.id))
  const templates = args.templates || MCP_SERVER_TEMPLATES
  const fromTemplates = templates.map((row) => templateToCatalogItem(row, installedIds))
  const templateIds = new Set(fromTemplates.map((row) => row.id))
  const extraInstalled = installed
    .filter((row) => !templateIds.has(row.id))
    .map(installedToCatalogItem)
  const fromMarket = (args.marketplace?.items || []).map(marketplaceToCatalogItem)
  const warnings = [...(args.marketplace?.warnings || [])]
  if (args.marketplace?.external && fromMarket.length > 0 && !warnings.includes(COMMUNITY_DANGER)) {
    warnings.unshift(COMMUNITY_DANGER)
  }
  return {
    items: [...fromTemplates, ...extraInstalled, ...fromMarket],
    warnings,
  }
}

export function itemToServerEntry(item: InstallCatalogItem): McpServerEntry | null {
  if (!item.installable) return null
  const id = newMcpServerId(item.name)
  const kind = item.kind === 'remote' ? 'remote' : 'local'
  const env: Record<string, string> = {}
  for (const name of item.requiredEnv) {
    if (ENV_NAME_RE.test(name)) env[name] = `\${${name}}`
  }
  return {
    id,
    name: item.name,
    kind,
    source: item.kind === 'openapi' ? 'openapi' : 'generic',
    enabled: true,
    command: kind === 'local' ? item.command || '' : '',
    args: kind === 'local' ? [...(item.args || [])] : [],
    url: kind === 'remote' ? item.url || '' : '',
    openapi_spec_url: item.openapiSpecUrl || '',
    env,
    headers: {},
    provides: [...item.toolsProvided],
    tools: [],
    note: item.note || item.summary,
  }
}

export interface CatalogInstallApis {
  upsert: (body: Record<string, unknown>) => Promise<McpPluginsPayload>
  discover: (body: Record<string, unknown>) => Promise<McpPluginDiscoverPayload>
}

export async function installAndProbe(
  item: InstallCatalogItem,
  apis: CatalogInstallApis,
): Promise<InstallOutcome> {
  const entry = itemToServerEntry(item)
  if (!entry) {
    return {
      status: 'fail',
      health: 'unknown',
      message: item.installHint || 'Not installable from this payload.',
    }
  }
  try {
    await apis.upsert(entryToUpsertBody(entry))
  } catch (err) {
    return {
      status: 'fail',
      health: 'unknown',
      message: err instanceof Error ? err.message : 'Install failed.',
    }
  }
  try {
    const discovered = await apis.discover({
      name: entry.id,
      kind: entry.kind,
      source: entry.source,
      command: entry.command,
      args: entry.args,
      url: entry.url,
      openapi_spec_url: entry.openapi_spec_url,
      env: entry.env,
      headers: entry.headers,
    })
    const count = discovered.tools.length
    return {
      status: 'ok',
      health: 'up',
      message: count
        ? `Connected — ${count} tool${count === 1 ? '' : 's'}.`
        : 'Connected — no tools listed.',
    }
  } catch (err) {
    return {
      status: 'ok',
      health: 'down',
      message: `Saved, but could not connect: ${err instanceof Error ? err.message : 'discover failed.'}`,
    }
  }
}
