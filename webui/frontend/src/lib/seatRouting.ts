/**
 * #804 — cross-kind routing picks must land on a real seat.
 *
 * The seat URL vocabulary is `?blueprint=` (api seats, incl. the api_agent
 * gateway), `?cli=` (host CLI seats), `?remote=` and `?team=`. Nothing reads
 * `?agent=` — yet cross-kind picks used to write exactly that dead param, and
 * the two-stage picker dropped API picks from non-API seats entirely.
 *
 * This helper turns a cross-kind pick into an explicit URL patch so every
 * kind resolves to a seat ChatPage actually reads, and stale params from the
 * previous seat (`?session=`, a previous kind's marker, an old `?model=`)
 * cannot bleed through.
 */

import { apiGet } from './api/client'
import { isRemoteSeatId, peeledSeatId } from './agentKind'
import {
  formatEngineSwitchWarning,
  lostEngineCapabilities,
  normalizeEngineKind,
  type EngineHopRow,
} from './engineSwitchWarning'

/** Params that mark a seat kind; picking one kind clears the others. */
const SEAT_KIND_PARAMS = ['blueprint', 'cli', 'remote', 'team'] as const
/** Per-seat state cleared on any seat change so nothing bleeds across (#804). */
const SEAT_STATE_PARAMS = ['session', 'model'] as const
const deleteListFrom = (kinds: readonly string[], set: Record<string, string>): string[] => [
  ...kinds.filter((p) => !(p in set)),
]

export type SeatPickKind = 'api' | 'cli' | 'remote' | 'team'

/**
 * #1436: a palette row tagged blueprint (or api) whose id is a remote, CLI,
 * or team seat navigates as that seat. `blueprint:` is a persistence tag and
 * is peeled before the `cli:` / `team:` / remote-impl checks. An explicit
 * cli / team / remote hint is kept when the id does not name a different seat.
 */
export function seatPickKindForTarget(
  kind: string | null | undefined,
  targetId: string,
): SeatPickKind {
  const peeled = peeledSeatId(targetId).trim().toLowerCase()
  if (isRemoteSeatId(targetId)) return 'remote'
  if (peeled.startsWith('team:') || kind === 'team') return 'team'
  if (peeled.startsWith('cli:') || kind === 'cli') return 'cli'
  if (kind === 'remote') return 'remote'
  return 'api'
}

/** Strip taxonomy prefixes so `?remote=` receives the seat id, not `blueprint:remote:`. */
export function canonicalSeatTargetId(kind: SeatPickKind, rawId: string): string {
  let id = peeledSeatId(rawId).trim()
  const lower = id.toLowerCase()
  if (kind === 'remote' && lower.startsWith('placeholder:remote:')) {
    return id.slice('placeholder:remote:'.length)
  }
  if (kind === 'remote' && lower.startsWith('remote:')) return id.slice('remote:'.length)
  if (kind === 'cli' && lower.startsWith('cli:')) return id.slice('cli:'.length)
  if (kind === 'team' && lower.startsWith('team:')) return id.slice('team:'.length)
  return id
}

export interface SeatParamPatch {
  /** Params to set for the picked seat (id may be empty for defaults). */
  set: Record<string, string>
  /** Stale params to delete (other kinds' markers + per-seat state). */
  delete: string[]
}

export interface SeatPickOpts {
  /**
   * API gateway profile picked from stage 2 (`API gateway → Claude Work`):
   * lands on the `api_agent` gateway with that profile applied as its model.
   * Absent for flat-palette picks of named api blueprints.
   */
  apiModel?: string
}

/**
 * #899: honest copy for a provider pick the current seat cannot apply.
 * The picker only surfaces API-gateway profiles as a reconfiguration —
 * it must never silently jump seats (#899's bug), so the attempt is
 * acknowledged with what happened and what will actually work.
 */
export function providerReconfigureNotice(
  profile: string,
  currentKind: 'api' | 'cli' | 'remote' | 'team',
): string {
  const seatLabel =
    currentKind === 'cli'
      ? 'CLI agent'
      : currentKind === 'remote'
        ? 'remote agent'
        : currentKind === 'team'
          ? 'team'
          : 'API agent'
  return `Provider profile '${profile}' noted — the ${seatLabel} keeps its own backend. Use the agent picker (stage 1 → API gateway) to switch to that profile as a seat.`
}

/**
 * The canonical seat-param patch for a cross-kind pick.
 *
 * - `api`: `?blueprint=<id>` (empty id → the `api_agent` gateway); a gateway
 *   profile pick adds `?model=<profile>` for the gateway to apply.
 * - `cli`: `?cli=<name>` — the param ChatPage's CLI resolution chain consumes.
 * - `remote` / `team` keep their existing params.
 * - `session` is per-seat state: always cleared so a new seat never inherits
 *   the previous seat's conversation. `model` is cleared too unless the pick
 *   explicitly sets it.
 */
export function seatParamsForPick(
  kind: SeatPickKind,
  id: string,
  opts: SeatPickOpts = {},
): SeatParamPatch {
  const trimmed = (id ?? '').trim()
  const set: Record<string, string> = {}
  if (kind === 'api') {
    set.blueprint = trimmed || 'api_agent'
    if (opts.apiModel) set.model = opts.apiModel
  } else if (kind === 'cli') {
    set.cli = trimmed
  } else if (kind === 'remote') {
    set.remote = trimmed
  } else {
    set.team = trimmed
  }
  const deleteList = deleteListFrom(SEAT_KIND_PARAMS, set)
  deleteList.push(...SEAT_STATE_PARAMS.filter((p) => !(p in set)))
  return { set, delete: deleteList }
}

/** Apply a seat patch so a leftover `?team=` / `?remote=` cannot share the URL. */
export function applySeatParamPatch(
  params: URLSearchParams,
  patch: SeatParamPatch,
): URLSearchParams {
  const next = new URLSearchParams(params)
  for (const key of patch.delete) next.delete(key)
  for (const [key, value] of Object.entries(patch.set)) {
    if (value) next.set(key, value)
  }
  return next
}

/**
 * #1445: navbar identity key for the URL seat. Team wins over remote, which
 * wins over blueprint — the same precedence ChatPage uses for the header face.
 * Leftover agentKind state is not consulted.
 */
export function headerSeatKey(input: {
  teamId?: string | null
  remoteId?: string | null
  blueprintId?: string | null
}): string {
  const team = (input.teamId ?? '').trim()
  if (team) return `team:${team}`
  const remote = (input.remoteId ?? '').trim()
  if (remote) return `remote:${remote}`
  const blueprint = (input.blueprintId ?? '').trim()
  return blueprint ? `api:${blueprint}` : 'api:'
}

/**
 * #1445: seat key for the chat-header gate. Unlike `headerSeatKey`, an empty
 * input is `''` (not `api:`), and a `?cli=` seat counts. Team still beats
 * remote, which beats CLI, which beats an explicit blueprint.
 */
export function activeHeaderSeatKey(input: {
  teamId?: string | null
  remoteId?: string | null
  cliId?: string | null
  blueprintId?: string | null
}): string {
  const team = (input.teamId ?? '').trim()
  if (team) return `team:${team}`
  const remote = (input.remoteId ?? '').trim()
  if (remote) return `remote:${remote}`
  const cli = (input.cliId ?? '').trim()
  if (cli) return `cli:${cli}`
  const blueprint = (input.blueprintId ?? '').trim()
  if (blueprint) return `api:${blueprint}`
  return ''
}

/** A header seat is `kind:id` with a non-empty id. `api:` and `''` are not. */
export function isValidHeaderSeatKey(seatKey: string | null | undefined): boolean {
  const key = (seatKey ?? '').trim()
  const colon = key.indexOf(':')
  if (colon <= 0) return false
  const kind = key.slice(0, colon)
  const id = key.slice(colon + 1).trim()
  if (!id) return false
  return kind === 'api' || kind === 'cli' || kind === 'remote' || kind === 'team'
}

// #815 — canonical seat identity. The URL vocabulary (?blueprint=, ?cli=,
// ?remote=, ?team=) already routes cross-kind picks (#804); these types name
// the seat itself so components can hold one descriptor instead of boolean
// soup. 'design' stays an authoring taxonomy tag under api, never a SeatKind.

export type SeatKind = 'api' | 'cli' | 'remote' | 'team'

export interface SeatDescriptor {
  kind: SeatKind
  id: string
  /** LLM profile applied to the api_agent gateway (model dimension). */
  model?: string
  /** Per-seat conversation id; never inherited across seats. */
  session?: string
}

/** The search param each SeatKind reads/writes. */
export const SEAT_KIND_PARAM: Record<SeatKind, string> = {
  api: 'blueprint',
  cli: 'cli',
  remote: 'remote',
  team: 'team',
}

/** Parse a SeatDescriptor from search params (legacy `?agent=` honoured). */
export function hydrateSeatFromSearchParams(
  params: URLSearchParams | Record<string, string>,
): SeatDescriptor | null {
  const get = (key: string): string => {
    if (typeof (params as URLSearchParams).get === 'function') {
      return ((params as URLSearchParams).get(key) ?? '').trim()
    }
    return ((params as Record<string, string>)[key] ?? '').trim()
  }
  const session = get('session') || undefined
  const model = get('model') || undefined
  if (get('team')) return { kind: 'team', id: get('team'), session }
  if (get('remote')) return { kind: 'remote', id: get('remote'), session }
  if (get('cli')) return { kind: 'cli', id: get('cli'), session }
  const blueprint = get('blueprint')
  if (blueprint) return { kind: 'api', id: blueprint, model, session }
  const legacyAgent = get('agent')
  if (legacyAgent) return { kind: 'api', id: legacyAgent, model, session }
  return null
}

/** Atomically set a seat: set its param, wipe every competing seat key + per-seat state. */
export function seatToSearchParams(
  seat: SeatDescriptor,
  apply: (set: Record<string, string>, deleteKeys: string[]) => void,
): void {
  const set: Record<string, string> = { [SEAT_KIND_PARAM[seat.kind]]: seat.id }
  if (seat.kind === 'api' && seat.id === 'api_agent' && seat.model) set.model = seat.model
  if (seat.session) set.session = seat.session
  const deleteKeys = (Object.keys(SEAT_KIND_PARAM) as SeatKind[])
    .map((k) => SEAT_KIND_PARAM[k])
    .filter((p) => !(p in set))
  // Per-seat state (#804): a new seat never inherits the previous seat's
  // conversation, and ?model= only survives when the pick set it.
  if (!set.session) deleteKeys.push('session')
  if (!set.model) deleteKeys.push('model')
  deleteKeys.push('agent') // dead param — nothing reads it (#804)
  apply(set, deleteKeys)
}

// #1352/#1353 — the *provider* a seat belongs to. The navbar Agent / Session
// pickers must be scoped to the selected agent's provider as configured in
// Edit agent (the inference list), never to the default inference profile. A
// provider scope is the (kind, id) pair that names one composer provider:
// `api`, `cli:<name>`, `remote:<id>`, `team:<id>`.

export type ProviderScopeKind = SeatKind

export interface ProviderScope {
  kind: ProviderScopeKind
  /** `api` gateway, a CLI name, a remote id, or a team id. */
  id: string
}

/** Canonical, stable key for a provider scope (e.g. `cli:opencode`). */
export function providerScopeKey(scope: ProviderScope): string {
  const kind = normalizeProviderScopeKind(scope.kind) ?? scope.kind
  const id = (scope.id || '').trim() || kind
  return `${kind}:${id}`
}

const PROVIDER_SCOPE_KIND_ALIASES: Record<string, ProviderScopeKind> = {
  api: 'api',
  blueprint: 'api',
  llm: 'api',
  cli: 'cli',
  remote: 'remote',
  herdr: 'remote',
  team: 'team',
}

/** Normalize a stored / source kind onto a provider scope kind. */
export function normalizeProviderScopeKind(
  kind: string | null | undefined,
): ProviderScopeKind | null {
  return PROVIDER_SCOPE_KIND_ALIASES[(kind ?? '').trim().toLowerCase()] ?? null
}

/**
 * Provider scope from one Edit-agent inference seat (REQ-69). An empty seat
 * or an unknown kind yields `null` — the caller then falls back to the row's
 * own kind rather than the default inference profile.
 *
 * An `llm` inference seat is the API gateway (the profile is the model
 * dimension, not a provider): it maps to `api:api`, never to the profile id —
 * a profile is not a provider, and the default inference profile must never
 * scope the list.
 */
export function providerScopeFromInference(
  seat: { id?: string; kind?: string } | null | undefined,
): ProviderScope | null {
  if (!seat) return null
  const kind = normalizeProviderScopeKind(seat.kind)
  if (!kind) return null
  if (kind === 'api') return { kind: 'api', id: 'api' }
  const id = (seat.id ?? '').trim()
  if (!id) return null
  return { kind, id }
}

/**
 * Provider scope for an agent option row. The Edit-agent inference override
 * (the agent's configured provider) always wins; otherwise the row's own
 * declared kind + provider id. The default inference profile is never
 * consulted — an agent with no explicit provider stays on its own kind.
 */
export function providerScopeForAgent(input: {
  id: string
  kind: string
  /**
   * The row's own provider id: a CLI name, remote id, or team id. API rows
   * normalize to the `api` gateway.
   */
  providerId?: string
  /** First Edit-agent inference seat, when the agent declares one. */
  inference?: { id?: string; kind?: string } | null
}): ProviderScope | null {
  const fromInference = providerScopeFromInference(input.inference)
  if (fromInference) return fromInference
  const kind = normalizeProviderScopeKind(input.kind)
  if (!kind) return null
  const declared = (input.providerId ?? '').trim()
  const id = declared || (kind === 'api' ? 'api' : (input.id ?? '').trim())
  if (!id) return null
  return { kind, id }
}

/**
 * #1352 — keep only the agents that belong to `scope`. A `null` scope keeps
 * every row (no provider context: honest "show all", never a default-profile
 * guess). Rows without a declared scope are treated as matching only when no
 * scope is known.
 */
export function filterAgentsByProviderScope<T extends { provider?: string }>(
  agents: readonly T[],
  scope: ProviderScope | string | null | undefined,
): T[] {
  const key = typeof scope === 'string' ? scope : scope ? providerScopeKey(scope) : ''
  if (!key) return [...agents]
  const declared = agents.filter((a) => Boolean((a.provider ?? '').trim()))
  if (declared.length === 0) return [...agents]
  return agents.filter((a) => (a.provider ?? '').trim() === key)
}

// #1324 — capability delta between two engines, from declared data only.
// `GET /v1/capabilities/seats/` publishes the maps. Kind strings never decide
// which axes exist; an undeclared axis is not offered.

export interface DeclaredSeatCapability {
  enabled?: boolean
  reason?: string
  label?: string
}

export interface DeclaredCliHop extends EngineHopRow {
  label?: string
}

/** Payload of `GET /v1/capabilities/seats/`. */
export interface SeatCapabilityDirectory {
  object?: string
  seat_capabilities: Record<string, Record<string, DeclaredSeatCapability>>
  cli?: Record<string, DeclaredCliHop>
  labels?: Record<string, string>
}

export interface CapabilitySide {
  kind: string
  id?: string
  label: string
  capabilities: Record<string, DeclaredSeatCapability>
  hop?: EngineHopRow | null
  labels?: Record<string, string>
}

export interface CapabilityDelta {
  lost: string[]
  warning: string | null
}

export function fetchSeatCapabilities(): Promise<SeatCapabilityDirectory> {
  return apiGet<SeatCapabilityDirectory>('/v1/capabilities/seats/')
}

export function capabilitySideFromDirectory(
  directory: SeatCapabilityDirectory,
  ref: { kind: string; id?: string; label?: string },
): CapabilitySide {
  const kind = normalizeEngineKind(ref.kind)
  const raw = directory.seat_capabilities?.[kind] ?? {}
  const labels = directory.labels ?? {}
  const capabilities: Record<string, DeclaredSeatCapability> = {}
  for (const [name, row] of Object.entries(raw)) {
    capabilities[name] = {
      enabled: Boolean(row?.enabled),
      reason: row?.reason,
      label: row?.label || labels[name],
    }
  }
  const cliId = (ref.id || '').trim().replace(/^cli:/, '')
  const hopRow =
    kind === 'cli' && cliId
      ? directory.cli?.[cliId] ?? directory.cli?.[cliId.toLowerCase()]
      : null
  const label = (ref.label || hopRow?.label || cliId || kind).trim() || kind
  return {
    kind,
    id: cliId || ref.id,
    label,
    capabilities,
    hop: hopRow
      ? { export: hopRow.export, list: hopRow.list, resume: hopRow.resume }
      : null,
    labels,
  }
}

/** Lost declared capabilities when moving from `from` to `to`. */
export function capabilityDelta(from: CapabilitySide, to: CapabilitySide): CapabilityDelta {
  const lost = lostEngineCapabilities({
    fromKind: from.kind,
    toKind: to.kind,
    fromRow: from.hop,
    toRow: to.hop,
    fromCapabilities: from.capabilities,
    toCapabilities: to.capabilities,
  })
  const labelMap: Record<string, string> = { ...(from.labels ?? {}), ...(to.labels ?? {}) }
  for (const id of lost) {
    const declared = from.capabilities[id]?.label || to.capabilities[id]?.label
    if (declared) labelMap[id] = declared
  }
  return {
    lost,
    warning: formatEngineSwitchWarning(lost, from.label, to.label, labelMap),
  }
}
