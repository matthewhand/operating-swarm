/**
 * #681/#682/#683 — the composer picker's provider list and per-provider
 * option sets, built from the same data the seat controls already use.
 *
 * Pure: ChatPage feeds in the query payloads (LLM profiles, discovered CLIs,
 * configured remotes, team rosters) and this module shapes the two-stage
 * workflow's inputs. No hardcoded stubs — an empty payload yields no rows.
 */
import type { ComposerProviderOption } from './composerPicker'
import type { ModelSearchOption } from './modelSearch'

export interface ComposerApiSource {
  /** LLM profiles as the API seat already lists them (#108, #584). */
  profiles?: ReadonlyArray<{ id: string; label: string }>
  defaultProfileId?: string
}

export interface ComposerCliSource {
  /** A CLI discovered on the host (discoveredClis / cli-agents payload). */
  name: string
  /** Session-resumable agents for that CLI, when the payload carries them. */
  agents?: ReadonlyArray<{ id: string; label: string }>
  /** Probed models for the CLI (#682) — offered as model-dimension rows. */
  models?: readonly string[]
}

export interface ComposerRemoteSource {
  id: string
  label: string
  /** The remote's agent bots (#683). */
  agents?: ReadonlyArray<{ id: string; label: string }>
  defaultAgentId?: string
}

export interface ComposerTeamSource {
  id: string
  label: string
  /** Team roster members (#683). */
  members?: ReadonlyArray<{ id: string; label: string }>
  defaultMemberId?: string
}

export interface ComposerSources {
  api?: ComposerApiSource
  clis?: readonly ComposerCliSource[]
  remotes?: readonly ComposerRemoteSource[]
  teams?: readonly ComposerTeamSource[]
}

/** Stage-1 rows, in a stable kind order: api, cli, remote, team. */
export function buildComposerProviders(sources: ComposerSources): ComposerProviderOption[] {
  const rows: ComposerProviderOption[] = []
  if (sources.api) {
    rows.push({
      id: 'api',
      label: 'API gateway',
      kind: 'api',
      defaultOptionId: sources.api.defaultProfileId,
      description: 'LLM profiles',
    })
  }
  for (const cli of sources.clis ?? []) {
    rows.push({
      id: `cli:${cli.name}`,
      label: cli.name,
      kind: 'cli',
      // A CLI with no session data defaults to itself: accepting "Use default"
      // selects that CLI (the provider *is* the agent-dimension choice).
      defaultOptionId: cli.agents?.[0]?.id ?? cli.name,
      description: cli.agents?.length
        ? `${cli.agents.length} session(s)`
        : cli.models?.length
          ? `${cli.models.length} model(s)`
          : undefined,
    })
  }
  for (const remote of sources.remotes ?? []) {
    rows.push({
      id: `remote:${remote.id}`,
      label: remote.label,
      kind: 'remote',
      defaultOptionId: remote.defaultAgentId,
      description: remote.agents?.length ? `${remote.agents.length} agent(s)` : undefined,
    })
  }
  for (const team of sources.teams ?? []) {
    rows.push({
      id: `team:${team.id}`,
      label: team.label,
      kind: 'team',
      defaultOptionId: team.defaultMemberId,
      description: team.members?.length ? `${team.members.length} member(s)` : undefined,
    })
  }
  return rows
}

/** Stage-2 options for one provider, drawn from the same live payload. */
export function composerOptionsForProvider(
  sources: ComposerSources,
  provider: ComposerProviderOption,
): ModelSearchOption[] {
  if (provider.kind === 'api') {
    return (sources.api?.profiles ?? []).map((p) => ({ id: p.id, label: p.label }))
  }
  if (provider.kind === 'cli') {
    const name = provider.id.slice('cli:'.length)
    const cli = (sources.clis ?? []).find((c) => c.name === name)
    return [
      ...(cli?.agents ?? []).map((a) => ({ id: a.id, label: a.label })),
      ...(cli?.models ?? []).map((m) => ({ id: m, label: m, tag: 'model' as const })),
    ]
  }
  if (provider.kind === 'remote') {
    const id = provider.id.slice('remote:'.length)
    const remote = (sources.remotes ?? []).find((r) => r.id === id)
    return (remote?.agents ?? []).map((a) => ({ id: a.id, label: a.label }))
  }
  if (provider.kind === 'team') {
    const id = provider.id.slice('team:'.length)
    const team = (sources.teams ?? []).find((t) => t.id === id)
    return (team?.members ?? []).map((m) => ({ id: m.id, label: m.label }))
  }
  return []
}
