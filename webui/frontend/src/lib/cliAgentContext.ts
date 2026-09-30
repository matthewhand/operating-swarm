/**
 * Chat dropdown context: CLI-agent chats list discovered CLIs, not blueprints.
 *
 * Detection (any one is enough):
 * - selected / ?blueprint= id is `cli_agent` or any `cli_*` family slug
 * - explicit `?mode=cli` / `?mode=cli_agent`
 * - explicit `?cli=<name>` (the host CLI to run)
 *
 * API seats (#108): a blueprint id whose rail row is `kind: 'api'` (e.g.
 * `api_agent`) is never a CLI context — a leftover `?cli=` must not flip it.
 */

import type { CliAgentsInfo, CliModelsResponse } from './api'
import { KNOWN_CLI_NAMES } from './cliAgents'
import type { LlmModelType } from './llmProfiles'
import { isCategorizerProfile } from './llmProfiles'
import { isHiddenRoutingLabel } from './routingPath'

/** Footer sentinel — Chat opens the in-app CLI agents settings pane. */
export const MANAGE_CLI_VALUE = '__manage_cli__'

/** SPA CLI agents pane. Chat "Manage CLI" uses openSettingsSheet, not a dump hop. */
export const MANAGE_CLI_HREF = '/chat?settings=cli-agents'

/** True for `cli_agent`, `cli_*` family (`cli_fusion`, `cli_map`, …), and known CLI names (`grok`, `agy`, …). */
export function isCliBlueprintId(id: string): boolean {
  const norm = id.trim().toLowerCase()
  if (norm.startsWith('cli_') || norm.startsWith('cli:') || norm === 'cli') return true
  return (KNOWN_CLI_NAMES as readonly string[]).includes(norm)
}

/**
 * #566: where a seat's CLI came from. `inferred` is the fallback that picks an
 * installed CLI for a seat that declares none — it must never be presented as
 * fact, only ever shown/recorded as "inferred". `none` means the seat resolved
 * no CLI at all (every non-CLI seat, and a CLI seat with nothing installed).
 */
export type CliResolutionSource = 'param' | 'persisted' | 'declared' | 'inferred' | 'none'

export interface CliResolution {
  cli: string
  source: CliResolutionSource
}

/**
 * #566: the single CLI resolution chain, extracted so the send path, the
 * labels, and the audit log cannot drift. A seat that is not a CLI seat never
 * resolves a CLI — that rule is the fix for remote agents presenting a CLI
 * name ("qwen") they do not use.
 */
export function resolveCurrentCli(options: {
  isCliSeat: boolean
  param: string
  persisted: string
  declared: string
  discovered: string[]
  preferred: (discovered: string[]) => string
}): CliResolution {
  if (!options.isCliSeat) return { cli: '', source: 'none' }
  const param = options.param.trim()
  if (param) return { cli: param, source: 'param' }
  const persisted = options.persisted.trim()
  if (persisted) return { cli: persisted, source: 'persisted' }
  const declared = options.declared.trim()
  if (declared) return { cli: declared, source: 'declared' }
  const inferred = options.preferred(options.discovered)
  if (inferred) return { cli: inferred, source: 'inferred' }
  return { cli: '', source: 'none' }
}

/** True when ChatPage should list host CLIs instead of the blueprint catalog. */
export function isCliAgentContext(options: {
  blueprintId?: string | null
  searchParams?: URLSearchParams | null
}): boolean {
  if (isApiBlueprintId(options.blueprintId ?? '')) return false
  if (isCliBlueprintId(options.blueprintId ?? '')) return true
  const params = options.searchParams
  if (!params) return false
  const mode = (params.get('mode') ?? '').trim().toLowerCase()
  if (mode === 'cli' || mode === 'cli_agent') return true
  return (params.get('cli') ?? '').trim().length > 0
}

/**
 * True for rail rows / ids that are API seats (#108): `kind === 'api'` or the
 * `api_agent` id. Kept next to `isCliAgentContext` so ChatPage can gate its
 * CLI-vs-API picker decision on one honest pair of predicates.
 */
export function isApiBlueprintId(id: string | null | undefined): boolean {
  const norm = (id ?? '').trim().toLowerCase()
  return norm === 'api_agent' || norm === 'api' || norm.startsWith('api:')
}

export interface DesignedCliSeat {
  id: string
  name: string
  cli: string
  description: string
}

/**
 * A designer-created CLI seat (`/v1/agents/designs/`, e.g. `antigravity` →
 * `agy`, `hass-eng` → `opencode`) declares its host CLI in `cli`. Such seats
 * are not in the `/v1/cli-agents/` rail, so ChatPage cannot find them there.
 * Returns the seat when `blueprintId` matches a design with a non-empty `cli`,
 * else null (API/framework designs have no `cli` and must stay API seats).
 */
export function designedCliSeat(
  blueprintId: string | null | undefined,
  designs:
    | Array<{
        agent_id?: string
        name?: string
        cli?: string
        description?: string
        specialty?: string
      }>
    | null
    | undefined,
): DesignedCliSeat | null {
  const id = (blueprintId ?? '').trim()
  if (!id) return null
  const design = (designs ?? []).find((row) => (row?.agent_id ?? '').trim() === id)
  const cli = (design?.cli ?? '').trim()
  if (!design || !cli) return null
  return {
    id,
    name: (design.name ?? '').trim() || id,
    cli,
    description: (design.description ?? design.specialty ?? '').trim(),
  }
}

/**
 * CLIs the chat dropdown should list (#149 / REQ-157).
 *
 * Starting set is **discovered** host CLIs (PATH seed). Configured names that
 * are not on PATH still appear after the user adds them. Always include the
 * selected / running CLI so a mid-chat switch stays visible.
 * Do not fall back to the static catalog (`known` / `clis`) — pi absent stays absent.
 */
export function discoverChatClis(
  info: CliAgentsInfo | null | undefined,
  selected?: string | null,
): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  const push = (name: unknown) => {
    const raw =
      typeof name === 'string'
        ? name
        : (name as { name?: string; id?: string; cli?: string } | null | undefined)?.name ??
          (name as { name?: string; id?: string; cli?: string } | null | undefined)?.id ??
          (name as { name?: string; id?: string; cli?: string } | null | undefined)?.cli
    if (typeof raw !== 'string') return
    const trimmed = raw.trim()
    if (!trimmed || trimmed === MANAGE_CLI_VALUE || seen.has(trimmed)) return
    seen.add(trimmed)
    out.push(trimmed)
  }
  for (const name of info?.discovered ?? info?.installed ?? []) {
    push(name)
  }
  for (const name of info?.configured ?? []) {
    push(name)
  }
  push(info?.default_cli)
  push(selected)
  return out
}

/** Keep the running/selected CLI; otherwise prefer grok, then the first name. */
export function preferredChatCli(names: string[], current?: string | null): string {
  const trimmed = (current ?? '').trim()
  if (trimmed) return trimmed
  if (names.includes('grok')) return 'grok'
  return names[0] ?? ''
}

/**
 * CLI model options for a CLI seat's Model control (REQ-171C-3 / #612).
 *
 * The *only* source is the per-CLI probe payload from
 * ``fetchCliModels(cli)`` (``GET /v1/cli-agents/<cli>/models/``). API /
 * LLM-profile ids are a different namespace and are never merged in here —
 * a CLI only accepts ids it actually exposes, so an API id offered for a CLI
 * just fails at ``<cli> --model``.
 *
 * When the probe is empty, ``presets`` — that CLI's own catalog presets, as
 * the backend picker already returns for a CLI with no live probe — is the
 * honest fallback. Never invent option ``default``; ``list_models`` argv
 * tables from GET /v1/cli-agents/ are commands, not model ids.
 */
export function cliModelOptionsFor(
  payload?: Pick<CliModelsResponse, 'models' | 'warning'> | null,
  presets?: readonly string[] | null,
): { models: string[]; warning: string | null } {
  const models: string[] = []
  const seen = new Set<string>()
  const push = (raw: unknown) => {
    if (typeof raw !== 'string') return
    const id = raw.trim()
    if (!id || isHiddenRoutingLabel(id) || seen.has(id)) return
    seen.add(id)
    models.push(id)
  }
  for (const raw of payload?.models ?? []) push(raw)
  if (models.length === 0) {
    for (const raw of presets ?? []) push(raw)
  }
  const warning = (payload?.warning ?? '').trim()
  return { models, warning: warning || null }
}

/**
 * Live list-models payload for the Chat CLI Model control (REQ-171C-3 / #612).
 *
 * Thin wrapper over :func:`cliModelOptionsFor` kept for the ChatPage call site.
 * Empty / failed probes stay empty; the backend already supplies that CLI's
 * catalog presets when it has no live probe.
 */
export function honestChatCliModels(
  payload?: Pick<CliModelsResponse, 'models' | 'warning'> | null,
): { models: string[]; warning: string | null } {
  return cliModelOptionsFor(payload)
}

/** Sources that are NOT API-namespace; the API Model control must exclude them. */
const FOREIGN_API_PROFILE_SOURCES = new Set(['cli', 'remote', 'list_models'])

/**
 * True when a `/v1/llm-profiles/` row is an API-namespace LLM profile.
 *
 * The payload mixes `source: config` API profiles with `source: cli` /
 * `remote` / `list_models` rows (connected CLIs and their live model lists).
 * An API seat can only route `api` ids — offering a CLI/remote id there just
 * fails at the gateway. Prefers the explicit backend `namespace` marker and
 * falls back to `source` for older servers.
 */
export function isApiNamespaceProfile(profile: {
  source?: string
  namespace?: string
} | null | undefined): boolean {
  if (!profile) return false
  const namespace = (profile.namespace ?? '').trim().toLowerCase()
  if (namespace) return namespace === 'api'
  const source = (profile.source ?? '').trim().toLowerCase()
  return !FOREIGN_API_PROFILE_SOURCES.has(source)
}

export interface ApiModelProfileInput {
  id?: string
  name?: string
  model?: string
  source?: string
  namespace?: string
  /** #1745 `chat` / `categorizer`. A System1 gate is never a chat option. */
  model_type?: LlmModelType | string
  owned_by?: string
}

/** LLM / profile ids for the API Model control — never /v1/models blueprint ids. */
export function apiModelOptionsFromProfiles(
  profiles: Array<ApiModelProfileInput> | null | undefined,
  extraIds: string[] = [],
): Array<{ id: string; label: string }> {
  const out: Array<{ id: string; label: string }> = []
  const seen = new Set<string>()
  const push = (id: string, label?: string) => {
    const trimmed = id.trim()
    if (!trimmed || isHiddenRoutingLabel(trimmed) || seen.has(trimmed)) return
    seen.add(trimmed)
    out.push({ id: trimmed, label: (label || trimmed).trim() || trimmed })
  }
  for (const profile of profiles ?? []) {
    if (!isApiNamespaceProfile(profile)) continue
    // #1745: a System1 categorizer gates a seat; offering it here would put a
    // gate in the chat composer / AgentEditor API list.
    if (isCategorizerProfile(profile)) continue
    if (profile.id) push(profile.id, profile.name || profile.id)
    if (profile.model) push(profile.model)
  }
  for (const extra of extraIds) push(extra)
  return out
}
