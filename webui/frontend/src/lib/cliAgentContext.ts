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

import type { CliAgentsInfo, CliModelsResponse, LlmProfile } from './api'
import { KNOWN_CLI_NAMES } from './cliAgents'
import { isHiddenRoutingLabel } from './routingPath'

/** Footer sentinel — Chat opens the in-app CLI agents settings pane. */
export const MANAGE_CLI_VALUE = '__manage_cli__'

/** Django operator dump. Chat "Manage CLI" uses openSettingsSheet, not this href. */
export const MANAGE_CLI_HREF = '/settings/'

/** True for `cli_agent`, `cli_*` family (`cli_fusion`, `cli_map`, …), and known CLI names (`grok`, `agy`, …). */
export function isCliBlueprintId(id: string): boolean {
  const norm = id.trim().toLowerCase()
  if (norm.startsWith('cli_') || norm.startsWith('cli:') || norm === 'cli') return true
  return (KNOWN_CLI_NAMES as readonly string[]).includes(norm)
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
 * Live list-models payload for the Chat CLI Model control (REQ-171C-3 / #612).
 *
 * Empty / failed probes stay empty. Never invent option ``default``.
 * ``list_models`` argv tables from GET /v1/cli-agents/ are not model ids.
 */
export function honestChatCliModels(
  payload?: Pick<CliModelsResponse, 'models' | 'warning'> | null,
): { models: string[]; warning: string | null } {
  const models: string[] = []
  const seen = new Set<string>()
  for (const raw of payload?.models ?? []) {
    if (typeof raw !== 'string') continue
    const id = raw.trim()
    if (!id || isHiddenRoutingLabel(id) || seen.has(id)) continue
    seen.add(id)
    models.push(id)
  }
  const warning = (payload?.warning ?? '').trim()
  if (models.length === 0) {
    return { models: [], warning: warning || null }
  }
  return { models, warning: warning || null }
}

/** LLM / profile ids for the API Model control — never /v1/models blueprint ids. */
export function apiModelOptionsFromProfiles(
  profiles: Array<Pick<LlmProfile, 'id' | 'name' | 'model'>> | null | undefined,
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
    if (profile.id) push(profile.id, profile.name || profile.id)
    if (profile.model) push(profile.model)
  }
  for (const extra of extraIds) push(extra)
  return out
}
