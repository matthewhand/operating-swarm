/**
 * Chat dropdown context: CLI-agent chats list discovered CLIs, not blueprints.
 *
 * Detection (any one is enough):
 * - selected / ?blueprint= id is `cli_agent` or any `cli_*` family slug
 * - explicit `?mode=cli` / `?mode=cli_agent`
 * - explicit `?cli=<name>` (the host CLI to run)
 */

import type { CliAgentsInfo, CliModelsResponse, LlmProfile } from './api'
import { KNOWN_CLI_NAMES } from './cliAgents'
import { isHiddenRoutingLabel } from './routingPath'

/** Last native-select item — navigates to the existing CLI manage path. */
export const MANAGE_CLI_VALUE = '__manage_cli__'

/** Settings is the operator config surface (Builder SPA was deleted, ADR-001). */
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
  if (isCliBlueprintId(options.blueprintId ?? '')) return true
  const params = options.searchParams
  if (!params) return false
  const mode = (params.get('mode') ?? '').trim().toLowerCase()
  if (mode === 'cli' || mode === 'cli_agent') return true
  return (params.get('cli') ?? '').trim().length > 0
}

/**
 * CLIs the chat dropdown should list (REQ-157 / #565).
 *
 * Only **configured** names (Settings / + add). Discovered PATH binaries stay
 * off the dropdown until the user adds them — same opt-in as remotes.
 * Always include the selected / running CLI so a mid-chat switch stays visible.
 * Do not fall back to the static catalog (that was surprise clutter).
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
