/**
 * Routine builder tool picker (#1406).
 *
 * Composes GET /v1/routines/tool-catalog/ with the existing plugin/MCP
 * catalog (`loadPluginCatalog`). Not a second registry — same ids chat uses.
 * Reasons never include token values.
 */
import { apiGet } from './api'
import {
  FIXTURE_PLUGIN_TOOLS,
  loadPluginCatalog,
  type PluginCatalogSource,
  type PluginTool,
} from './chatPluginTools'
import { SUGGESTABLE_TOOL_LABELS } from './routineToolSuggestions'
import { TOOL_MEMORIES, TOOL_OPEN_PULL_REQUEST } from './routines'

export type RoutineToolKind = 'builtin' | 'plugin' | 'mcp'

export interface RoutineToolCatalogItem {
  id: string
  label: string
  description: string
  kind: RoutineToolKind
  source: string
  server_id: string
  server_name: string
  wired: boolean
  available: boolean
  reason: string
  can_live?: boolean
}

export interface RoutineToolCatalogResponse {
  object: 'routine_tool_catalog'
  items: RoutineToolCatalogItem[]
}

const OPEN_PR_ITEM: RoutineToolCatalogItem = {
  id: TOOL_OPEN_PULL_REQUEST,
  label: 'Open Pull Request',
  description: 'Open or update a GitHub pull request from this routine run. Never auto-merges.',
  kind: 'builtin',
  source: 'routine',
  server_id: '',
  server_name: '',
  wired: true,
  available: true,
  reason: '',
  can_live: true,
}

const MEMORIES_ITEM: RoutineToolCatalogItem = {
  id: TOOL_MEMORIES,
  label: 'Memories',
  description:
    'Remember and recall prior context. The id is stored on the routine; the run path does not attach recall yet.',
  kind: 'builtin',
  source: 'routine',
  server_id: '',
  server_name: '',
  wired: false,
  available: true,
  reason: '',
  can_live: false,
}

const TOKENISH = /ghp_|github_pat_|sk-|xai-|Bearer\s+[A-Za-z0-9._-]{12,}/i

export function scrubCatalogReason(reason: string): string {
  const text = String(reason || '').trim()
  if (!text) return ''
  if (TOKENISH.test(text)) {
    return 'This connector needs configuration in Settings → Plugins.'
  }
  return text
}

export function itemFromPluginTool(
  tool: PluginTool,
  source: PluginCatalogSource | string = 'fixture',
): RoutineToolCatalogItem {
  return {
    id: tool.id,
    label: tool.name,
    description: tool.description,
    kind: 'plugin',
    source,
    server_id: tool.serverId,
    server_name: tool.serverName,
    wired: true,
    available: true,
    reason: '',
    can_live: true,
  }
}

export function mergeRoutineToolCatalog(
  backend: RoutineToolCatalogItem[] | null | undefined,
  pluginTools: PluginTool[] = [],
  pluginSource: PluginCatalogSource | string = 'fixture',
): RoutineToolCatalogItem[] {
  const byId = new Map<string, RoutineToolCatalogItem>()
  for (const item of backend || []) {
    const id = String(item.id || '').trim()
    if (!id) continue
    byId.set(id, {
      ...item,
      label: scrubCatalogReason(item.label) || id,
      description: scrubCatalogReason(item.description),
      reason: scrubCatalogReason(item.reason),
    })
  }
  for (const tool of pluginTools) {
    if (!tool.id || byId.has(tool.id)) continue
    byId.set(tool.id, itemFromPluginTool(tool, pluginSource))
  }
  if (!byId.has(TOOL_OPEN_PULL_REQUEST)) {
    byId.set(TOOL_OPEN_PULL_REQUEST, OPEN_PR_ITEM)
  }
  if (!byId.has(TOOL_MEMORIES)) {
    byId.set(TOOL_MEMORIES, MEMORIES_ITEM)
  }
  return [...byId.values()]
}

export function fallbackRoutineToolCatalog(): RoutineToolCatalogItem[] {
  return mergeRoutineToolCatalog(
    [
      OPEN_PR_ITEM,
      {
        id: 'brave_search',
        label: 'Brave Search',
        description: 'Brave Search — needs an API key.',
        kind: 'mcp',
        source: 'mcp_catalog',
        server_id: 'brave_search',
        server_name: 'Brave Search',
        wired: false,
        available: false,
        reason: 'Needs BRAVE_API_KEY — set it in Settings → Plugins. Tokens stay out of this builder.',
        can_live: false,
      },
    ],
    FIXTURE_PLUGIN_TOOLS,
    'fixture',
  )
}

export async function fetchRoutineToolCatalog(): Promise<RoutineToolCatalogItem[]> {
  let backend: RoutineToolCatalogItem[] = []
  try {
    const data = await apiGet<RoutineToolCatalogResponse>('/v1/routines/tool-catalog/')
    if (Array.isArray(data?.items)) backend = data.items
  } catch {
    /* fall through to plugin catalog / fixture */
  }
  try {
    const resolved = await loadPluginCatalog()
    const merged = mergeRoutineToolCatalog(backend, resolved.tools, resolved.source)
    if (merged.length > 0) return merged
  } catch {
    /* fixture */
  }
  return mergeRoutineToolCatalog(backend, FIXTURE_PLUGIN_TOOLS, 'fixture')
}

export function filterRoutineToolCatalog(
  items: readonly RoutineToolCatalogItem[],
  query: string,
): RoutineToolCatalogItem[] {
  const q = query.trim().toLowerCase()
  if (!q) return [...items]
  return items.filter((item) => {
    return (
      item.label.toLowerCase().includes(q) ||
      item.description.toLowerCase().includes(q) ||
      item.server_name.toLowerCase().includes(q) ||
      item.id.toLowerCase().includes(q)
    )
  })
}

export function catalogLabelFor(
  items: readonly RoutineToolCatalogItem[],
  toolId: string,
): string {
  const found = items.find((item) => item.id === toolId)
  return found?.label || SUGGESTABLE_TOOL_LABELS[toolId] || toolId
}
