/**
 * #681/#682/#683 — the composer picker's provider list and per-provider
 * option sets, built from the same data the seat controls already use.
 *
 * Pure: ChatPage feeds in the query payloads (LLM profiles, discovered CLIs,
 * configured remotes, team rosters) and this module shapes the two-stage
 * workflow's inputs. No hardcoded stubs — an empty payload yields no rows.
 */
import type { ComposerProviderOption } from './composerPicker'
import { isCategorizerProfile, type LlmModelType } from './llmProfiles'
import type { ModelSearchOption } from './modelSearch'

export interface ComposerApiSource {
  /** LLM profiles as the API seat already lists them (#108, #584). */
  profiles?: ReadonlyArray<{
    id: string
    label: string
    /** #1745 `chat` / `categorizer`; absent ⇒ chat. */
    modelType?: LlmModelType | string
    ownedBy?: string
  }>
  defaultProfileId?: string
}

export interface ComposerCliSource {
  /** A CLI discovered on the host (discoveredClis / cli-agents payload). */
  name: string
  /**
   * #711: resumable sessions for that CLI (REQ-104 payload: sessions +
   * recents, deduped, newest first). Offered as `session`-tagged stage-2
   * rows; picking one resumes that conversation. Optional — a CLI without
   * the payload offers no session rows (honest, no stubs).
   */
  sessions?: ReadonlyArray<{ id: string; label: string }>
  /** Probed models for the CLI (#682) — offered as model-dimension rows. */
  models?: readonly string[]
  /**
   * The sessions/models payload is still loading (#803): auto-pick must not
   * resolve on a partial option list.
   */
  optionsPending?: boolean
}

export interface ComposerRemoteSource {
  id: string
  label: string
  /** The remote's agent bots (#683). */
  agents?: ReadonlyArray<{ id: string; label: string }>
  defaultAgentId?: string
  /** Agent list still loading (#803) — suppresses auto-pick. */
  optionsPending?: boolean
  /**
   * #789 — the remote's configured Herdr panes (GET /v1/herdr-agents/),
   * offered as stage-2 rows after any explicit agents. Picking one lands in
   * `?session=<name>` — the same target the #543 navbar popup wrote.
   */
  herdrAgents?: ReadonlyArray<{ id: number | string; name: string }>
}

export interface ComposerTeamSource {
  id: string
  label: string
  /** Team roster members (#683). */
  members?: ReadonlyArray<{ id: string; label: string }>
  defaultMemberId?: string
}

export interface ComposerBlueprintSource {
  id: string
  label: string
  description?: string
}

/**
 * #1288 — opt-in client-side WebGPU provider. Never populated unless the
 * `webgpu` experiment is enabled, and never server-routed. Omit it entirely to
 * guarantee the row is absent (the default for every existing caller).
 */
export interface ComposerWebGpuSource {
  models?: ReadonlyArray<{ id: string; label: string }>
  defaultModelId?: string
}

export interface ComposerSources {
  api?: ComposerApiSource
  clis?: readonly ComposerCliSource[]
  remotes?: readonly ComposerRemoteSource[]
  teams?: readonly ComposerTeamSource[]
  blueprints?: readonly ComposerBlueprintSource[]
  webgpu?: ComposerWebGpuSource
}

/**
 * #1745 — the API provider's stage-2 rows. A System1 categorizer answers a
 * gate, not chat tokens, so it is dropped here: the composer picker is a chat
 * surface and must never offer a gate as a model. The same filter guards the
 * "Use default" row, which must not silently resolve to a gate either.
 */
function chatApiProfiles(source: ComposerApiSource | undefined) {
  const rows = source?.profiles ?? []
  return rows.filter((row) => !isCategorizerProfile({ model_type: row.modelType, owned_by: row.ownedBy }))
}

function chatDefaultProfileId(source: ComposerApiSource | undefined): string | undefined {
  const rows = chatApiProfiles(source)
  const declared = source?.defaultProfileId
  if (declared && rows.some((row) => row.id === declared)) return declared
  return rows[0]?.id
}

/** Stage-1 rows, in a stable kind order: api, cli, remote, blueprint. */
export function buildComposerProviders(sources: ComposerSources): ComposerProviderOption[] {
  const rows: ComposerProviderOption[] = []
  if (sources.api) {
    const chatProfiles = chatApiProfiles(sources.api)
    rows.push({
      id: 'api',
      label: 'API gateway',
      kind: 'api',
      defaultOptionId: chatDefaultProfileId(sources.api),
      description: chatProfiles.length ? 'LLM profiles' : 'No chat models connected',
    })
  }
  for (const cli of sources.clis ?? []) {
    rows.push({
      id: `cli:${cli.name}`,
      label: cli.name,
      kind: 'cli',
      // #711: "Use default" always selects the CLI itself — never a session
      // id (sessions are an explicit stage-2 pick).
      defaultOptionId: cli.name,
      description: cli.sessions?.length
        ? `${cli.sessions.length} session(s)`
        : cli.models?.length
          ? `${cli.models.length} model(s)`
          : undefined,
      ...(cli.optionsPending ? { optionsPending: true } : {}),
    })
  }
  for (const remote of sources.remotes ?? []) {
    rows.push({
      id: `remote:${remote.id}`,
      label: remote.label,
      kind: 'remote',
      defaultOptionId: remote.defaultAgentId,
      description: remote.agents?.length ? `${remote.agents.length} agent(s)` : undefined,
      ...(remote.optionsPending ? { optionsPending: true } : {}),
    })
  }
  // #832: group custom blueprints and teams under a single 'Custom Blueprint' provider
  const customBlueprints = sources.blueprints ?? []
  const customTeams = sources.teams ?? []
  const blueprintCount = customBlueprints.length
  const teamCount = customTeams.length
  if (blueprintCount > 0 || teamCount > 0) {
    const descParts: string[] = []
    if (blueprintCount > 0) {
      descParts.push(`${blueprintCount} blueprint${blueprintCount === 1 ? '' : 's'}`)
    }
    if (teamCount > 0) {
      descParts.push(`${teamCount} rig${teamCount === 1 ? '' : 's'}`)
    }
    rows.push({
      id: 'custom_blueprint',
      label: 'Custom Blueprint',
      kind: 'blueprint',
      defaultOptionId: customBlueprints[0]?.id ?? customTeams[0]?.id,
      description: descParts.join(', '),
    })
  }
  // #1288: client-side WebGPU provider — only present when the caller passes
  // a source (which it must gate behind the experimental flag). It stays last
  // so it never reorders the server-side providers.
  if (sources.webgpu) {
    rows.push({
      id: 'webgpu',
      label: 'WebGPU (in-browser)',
      kind: 'webgpu',
      defaultOptionId: sources.webgpu.defaultModelId,
      description: 'Runs in this browser tab',
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
    return chatApiProfiles(sources.api).map((p) => ({ id: p.id, label: p.label }))
  }
  if (provider.kind === 'cli') {
    const name = provider.id.slice('cli:'.length)
    const cli = (sources.clis ?? []).find((c) => c.name === name)
    return [
      // #711: resumable sessions first, then probed models — each tagged so
      // the pick resolves on the right dimension.
      ...(cli?.sessions ?? []).map((s) => ({ id: s.id, label: s.label, tag: 'session' as const })),
      ...(cli?.models ?? []).map((m) => ({ id: m, label: m, tag: 'model' as const })),
    ]
  }
  if (provider.kind === 'remote') {
    const id = provider.id.slice('remote:'.length)
    const remote = (sources.remotes ?? []).find((r) => r.id === id)
    return [
      ...(remote?.agents ?? []).map((a) => ({ id: a.id, label: a.label })),
      // #789: configured herdr panes trail explicit agent bots.
      ...(remote?.herdrAgents ?? []).map((h) => ({ id: h.name, label: h.name })),
    ]
  }
  if (provider.kind === 'webgpu') {
    // #1288: stage-2 rows are the browser-runnable models. An empty catalogue
    // yields no rows (honest — no invented models).
    return (sources.webgpu?.models ?? []).map((m) => ({
      id: m.id,
      label: m.label,
      tag: 'model' as const,
    }))
  }
  if (provider.kind === 'blueprint' || provider.id === 'custom_blueprint') {
    const options: ModelSearchOption[] = []
    for (const b of sources.blueprints ?? []) {
      options.push({
        id: b.id,
        label: b.label,
        description: b.description,
        tag: 'blueprint',
        kind: 'blueprint',
      })
    }
    for (const t of sources.teams ?? []) {
      options.push({
        id: t.id,
        label: t.label,
        tag: 'team',
        kind: 'team',
      })
    }
    return options
  }
  if (provider.kind === 'team') {
    const id = provider.id.replace(/^team:/, '')
    const team = (sources.teams ?? []).find((t) => t.id === id)
    return (team?.members ?? []).map((m) => ({ id: m.id, label: m.label }))
  }
  return []
}
