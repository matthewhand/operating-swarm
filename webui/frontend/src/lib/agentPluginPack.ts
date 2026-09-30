/**
 * Secret-free plugin pack helpers for the #1397 SPA.
 *
 * Packs are plugin ids only. Connection fields and credential-shaped strings
 * are refused before they hit the wire, and status payloads are stripped
 * before they hit the DOM — even if a response is leaky.
 */

import type {
  AgentPluginHostStatus,
  AgentPluginIdRow,
  AgentPluginMemoryNamed,
  AgentPluginPack,
  AgentPluginStatusRow,
  AgentPluginsStatus,
} from './api'

export const PACK_KIND = 'agent_plugin_pack'
export const PACK_OBJECT = 'agent_plugin_pack'
export const PACK_SCHEMA = 1

export const REFUSED_PACK_KEYS = Object.freeze([
  'url',
  'command',
  'args',
  'headers',
  'env',
  'token',
  'tokens',
  'api_key',
  'secret',
  'password',
  'authorization',
  'credentials',
  'openapi_spec_url',
  'openapispecurl',
  'cwd',
  'bearer',
] as const)

const SECRET_KEY_TOKENS = ['secret', 'token', 'password', 'api_key', 'authorization'] as const

export const SECRET_VALUE_RE =
  /sk-[A-Za-z0-9_-]{4,}|bearer\s+[A-Za-z0-9._\-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}/i

const PUBLIC_ROW_KEYS = new Set(['pluginId', 'name', 'description'])

export class PluginPackClientError extends Error {
  code: string

  constructor(message: string, code = 'plugin_pack_invalid') {
    super(message)
    this.name = 'PluginPackClientError'
    this.code = code
  }
}

function isRefusedKey(key: string): boolean {
  const lower = key.trim().toLowerCase()
  return (
    (REFUSED_PACK_KEYS as readonly string[]).includes(lower) ||
    SECRET_KEY_TOKENS.some((token) => lower.includes(token))
  )
}

export function looksLikeSecret(value: string): boolean {
  return SECRET_VALUE_RE.test(value)
}

export function refuseSecrets(raw: unknown, where = 'pack'): void {
  if (Array.isArray(raw)) {
    raw.forEach((item, index) => refuseSecrets(item, `${where}[${index}]`))
    return
  }
  if (raw && typeof raw === 'object') {
    const hits = Object.keys(raw)
      .filter((key) => isRefusedKey(key))
      .sort()
    if (hits.length) {
      throw new PluginPackClientError(
        `${where} must be plugin ids only; refused field(s): ${hits.join(', ')}`,
        'plugin_pack_secrets',
      )
    }
    for (const [key, value] of Object.entries(raw)) {
      refuseSecrets(value, `${where}.${key}`)
    }
    return
  }
  if (typeof raw === 'string' && looksLikeSecret(raw)) {
    throw new PluginPackClientError(
      `${where} looks like a credential and was refused.`,
      'plugin_pack_secrets',
    )
  }
}

function pluginIdOf(raw: unknown): string {
  if (typeof raw === 'string') return raw.trim()
  if (!raw || typeof raw !== 'object') return ''
  const row = raw as Record<string, unknown>
  for (const key of ['pluginId', 'plugin_id', 'id', 'name']) {
    const value = String(row[key] ?? '').trim()
    if (value) return value
  }
  return ''
}

export function publicPluginRow(raw: unknown): AgentPluginIdRow {
  let incoming: Record<string, unknown> | null = null
  if (typeof raw === 'string') incoming = { pluginId: raw }
  else if (raw && typeof raw === 'object') incoming = { ...(raw as Record<string, unknown>) }
  if (!incoming) {
    throw new PluginPackClientError('plugin must be an id string or {pluginId, name?, description?}')
  }
  refuseSecrets(incoming, 'plugin')
  const pluginId = pluginIdOf(incoming)
  if (!pluginId) {
    throw new PluginPackClientError('pluginId is required', 'plugin_pack_id_missing')
  }
  if (looksLikeSecret(pluginId)) {
    throw new PluginPackClientError(
      'pluginId looks like a credential and was refused.',
      'plugin_pack_secrets',
    )
  }
  const name = String(incoming.name || incoming.label || '').trim()
  const description = String(incoming.description || incoming.summary || '').trim()
  return {
    pluginId,
    name: name || pluginId.split('/').pop()?.replace(/^(mcp:|github:)/, '') || pluginId,
    description,
  }
}

function pluginsFrom(raw: unknown): unknown[] {
  if (raw == null) return []
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'object') {
    const row = raw as Record<string, unknown>
    for (const key of ['plugins', 'pluginIds', 'plugin_ids', 'ids']) {
      const value = row[key]
      if (Array.isArray(value)) return value
      if (typeof value === 'string' && value.trim()) return [value]
    }
  }
  if (typeof raw === 'string' && raw.trim()) return [raw]
  throw new PluginPackClientError('pack must include plugins[] of plugin ids', 'plugin_pack_invalid')
}

export function validatePack(raw: unknown): AgentPluginPack {
  if (raw == null) {
    throw new PluginPackClientError('pack must be a JSON object or plugins list')
  }
  const incoming = Array.isArray(raw) ? { plugins: raw } : raw
  if (!incoming || typeof incoming !== 'object') {
    throw new PluginPackClientError('pack must be a JSON object or plugins list')
  }
  refuseSecrets(incoming, 'pack')
  const seen = new Set<string>()
  const plugins: AgentPluginIdRow[] = []
  for (const item of pluginsFrom(incoming)) {
    const row = publicPluginRow(item)
    if (seen.has(row.pluginId)) continue
    seen.add(row.pluginId)
    plugins.push(row)
  }
  const kind = String((incoming as { kind?: unknown }).kind || PACK_KIND).trim() || PACK_KIND
  return {
    object: PACK_OBJECT,
    schema: PACK_SCHEMA,
    kind,
    plugins,
  }
}

function splitLooseIds(text: string): string[] {
  return text
    .split(/[\s,]+/)
    .map((part) => part.trim())
    .filter(Boolean)
}

export function parsePackInput(text: string): AgentPluginPack {
  const trimmed = text.trim()
  if (!trimmed) {
    throw new PluginPackClientError('Paste plugin ids or a pack JSON first.', 'plugin_pack_empty')
  }
  if (looksLikeSecret(trimmed)) {
    throw new PluginPackClientError(
      'Import looks like a credential and was refused.',
      'plugin_pack_secrets',
    )
  }
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    let parsed: unknown
    try {
      parsed = JSON.parse(trimmed)
    } catch {
      throw new PluginPackClientError('Pack JSON is invalid.', 'plugin_pack_invalid')
    }
    return validatePack(parsed)
  }
  return validatePack({ plugins: splitLooseIds(trimmed) })
}

export function publicPackJson(pack: AgentPluginPack): string {
  return `${JSON.stringify(
    {
      object: PACK_OBJECT,
      schema: PACK_SCHEMA,
      kind: pack.kind || PACK_KIND,
      plugins: pack.plugins.map((row) => ({
        pluginId: row.pluginId,
        ...(row.name ? { name: row.name } : {}),
        ...(row.description ? { description: row.description } : {}),
      })),
    },
    null,
    2,
  )}\n`
}

function envNamesOnly(raw: unknown): string[] | undefined {
  if (!Array.isArray(raw)) return undefined
  const names = raw
    .map((item) => String(item ?? '').trim())
    .filter((name) => name && !looksLikeSecret(name) && !name.includes('='))
  return names.length ? names : undefined
}

function publicIdRow(raw: unknown): AgentPluginIdRow | null {
  try {
    if (!raw || typeof raw !== 'object') {
      return typeof raw === 'string' && raw.trim() ? publicPluginRow(raw) : null
    }
    const row = raw as Record<string, unknown>
    const safe: Record<string, unknown> = {}
    for (const key of PUBLIC_ROW_KEYS) {
      if (key in row) safe[key] = row[key]
    }
    if (!safe.pluginId && row.id) safe.pluginId = row.id
    return publicPluginRow(safe)
  } catch {
    return null
  }
}

function publicStatusRow(raw: unknown): AgentPluginStatusRow | null {
  const base = publicIdRow(raw)
  if (!base || !raw || typeof raw !== 'object') return null
  const row = raw as Record<string, unknown>
  const status = hostStatus(row.status)
  const requiredEnv = envNamesOnly(row.required_env)
  const out: AgentPluginStatusRow = { ...base, status }
  if (requiredEnv) out.required_env = requiredEnv
  return out
}

export function publicStatusFromPayload(raw: unknown): AgentPluginsStatus | null {
  if (!raw || typeof raw !== 'object') return null
  const incoming = raw as Record<string, unknown>
  const pluginsRaw = Array.isArray(incoming.plugins) ? incoming.plugins : []
  const plugins = pluginsRaw.map(publicStatusRow).filter((row): row is AgentPluginStatusRow => !!row)
  const enabled = plugins.filter((row) => row.status === 'enabled').map((row) => row.pluginId)
  const missing = plugins.filter((row) => row.status === 'missing').map((row) => row.pluginId)
  const packRaw = incoming.pack
  let pack: AgentPluginsStatus['pack']
  if (packRaw && typeof packRaw === 'object') {
    try {
      const validated = validatePack(packRaw)
      pack = {
        object: validated.object,
        schema: validated.schema,
        kind: validated.kind,
        plugins: validated.plugins,
      }
    } catch {
      pack = undefined
    }
  }
  const object =
    incoming.object === 'agent_plugin_pack_import' ? 'agent_plugin_pack_import' : 'agent_plugins'
  const memoryNamed = publicMemoryNamed(incoming.memory_named ?? (packRaw && typeof packRaw === 'object'
    ? (packRaw as Record<string, unknown>).memory_named
    : undefined))
  return {
    object,
    agent_id: String(incoming.agent_id || '').trim(),
    plugins,
    enabled: Array.isArray(incoming.enabled)
      ? incoming.enabled.map((id) => String(id)).filter((id) => id && !looksLikeSecret(id))
      : enabled,
    missing: Array.isArray(incoming.missing)
      ? incoming.missing.map((id) => String(id)).filter((id) => id && !looksLikeSecret(id))
      : missing,
    memory_named: memoryNamed,
    ...(pack ? { pack: { ...pack, ...(memoryNamed.length ? { memory_named: memoryNamed } : {}) } } : {}),
  }
}

export type PluginChecklistState = 'connected' | 'needsAuth' | 'missing'

export function hostStatus(value: unknown): AgentPluginHostStatus {
  if (value === 'enabled' || value === 'connected') return 'enabled'
  if (value === 'missing-auth' || value === 'needsAuth') return 'missing-auth'
  if (value === 'missing-plugin') return 'missing-plugin'
  return 'missing'
}

/** Checklist states for the post-import connector list (#1397). */
export function checklistState(status: unknown): PluginChecklistState {
  const host = hostStatus(status)
  if (host === 'enabled') return 'connected'
  if (host === 'missing-auth') return 'needsAuth'
  return 'missing'
}

export const MEMORY_ONLY_NOTE = 'named in memory only'

export function publicMemoryNamed(raw: unknown): AgentPluginMemoryNamed[] {
  if (!Array.isArray(raw)) return []
  const out: AgentPluginMemoryNamed[] = []
  const seen = new Set<string>()
  for (const item of raw) {
    const name = typeof item === 'string'
      ? item.trim()
      : item && typeof item === 'object'
        ? String((item as { name?: unknown }).name ?? '').trim()
        : ''
    if (!name || looksLikeSecret(name) || seen.has(name)) continue
    seen.add(name)
    out.push({ name, note: MEMORY_ONLY_NOTE })
  }
  return out
}

export function selectedPack(
  plugins: AgentPluginIdRow[],
  selectedIds: Iterable<string>,
): AgentPluginPack {
  const selected = new Set(Array.from(selectedIds, (id) => String(id)))
  const rows = plugins.filter((row) => selected.has(row.pluginId))
  return validatePack({ plugins: rows })
}

export function displayTextIsSafe(text: string): boolean {
  if (!text) return true
  if (looksLikeSecret(text)) return false
  const lower = text.toLowerCase()
  return !['bearer ', 'sk-live', 'authorization:'].some((token) => lower.includes(token))
}

export function packHasNoSecrets(value: unknown): boolean {
  try {
    refuseSecrets(value, 'payload')
    return true
  } catch {
    return false
  }
}
