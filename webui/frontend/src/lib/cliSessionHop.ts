/**
 * REQ-138 / #531 — cross-tool session hop (quota hop; no copy-paste).
 *
 * A CLI/API dropdown switch starts a new backend session and seeds it with
 * condensed prior context. Distinct from the #362 dropdown-change status line.
 */

import { apiGet, apiPost } from './api'
import { agentIdFromBlueprint, conversationIdForAgent } from './agentChat'
import { loadHopPrefs } from './sessionHopPrefs'

export const CLI_SESSION_HOPPED_EVENT = 'swarm:cli-session-hopped'

export const CONTEXT_CARRIED_RE =
  /^Started a new \S+ session \(\S+ → \S+\)\. Carried (summary|full) context \(\d+ tokens\)\./

export type HopMode = 'summary' | 'full'

export interface CliSessionHopResult {
  object: 'cli_session_hop'
  agent_id: string
  conversation_id: string
  from_cli: string
  to_cli: string
  kind: 'cli' | 'api'
  cli_session_id: null
  mode: HopMode
  tokens: number
  token_budget: number
  omitted: string[]
  empty: boolean
  status: string
  export_warning: string | null
  /** #1324: destination lost declared capabilities. Null/absent when nothing is lost. */
  capability_warning?: string | null
  /** Where the seeded context came from: native export, the #901 DB mirror, or the swarm thread. */
  import: 'transcript' | 'swarm' | 'db_mirror'
  injection: {
    text: string
    mode: HopMode
    tokens: number
    empty: boolean
  }
}

export interface CliSessionHopCapabilities {
  object: 'cli_session_hop_capabilities'
  modes: HopMode[]
  default_mode: HopMode
  default_token_budget: number
  full_token_budget: number
  omitted: string[]
  automated_failover: false
  same_conversation: true
  always_new_session: true
  clis: Record<
    string,
    {
      cli: string
      list: string
      resume: boolean
      export: 'transcript' | 'summary' | 'none'
      hop: string
    }
  >
}

export function formatContextCarriedStatus(
  fromCli: string,
  toCli: string,
  mode: HopMode,
  tokens: number,
): string {
  return `Started a new ${toCli} session (${fromCli} → ${toCli}). Carried ${mode} context (${tokens} tokens).`
}

export function isContextCarriedStatus(text: string | null | undefined): boolean {
  return CONTEXT_CARRIED_RE.test(String(text || '').trim())
}

export async function fetchHopCapabilities(): Promise<CliSessionHopCapabilities> {
  return apiGet<CliSessionHopCapabilities>('/v1/cli-sessions/hop/')
}

export async function hopCliSession(opts: {
  agentId: string
  fromCli: string
  toCli: string
  conversationId?: string
  mode?: HopMode
  tokenBudget?: number
  importSessionId?: string
  kind?: 'cli' | 'api'
  /** #900: destination seat kind for cross-kind hops (cli | api | remote). */
  toKind?: 'cli' | 'api' | 'remote'
  /** #900: the seat id whose record consumes the pending seed. */
  toAgent?: string
  /** #900: human backend names for the banner (pretty labels). */
  toLabel?: string
  fromLabel?: string
  /** #900: seat id whose record owns the source transcript. */
  fromAgent?: string
}): Promise<CliSessionHopResult> {
  const prefs = loadHopPrefs()
  const from = conversationIdForAgent(opts.agentId)
  return apiPost<CliSessionHopResult>('/v1/cli-sessions/hop/', {
    agent: agentIdFromBlueprint(opts.agentId),
    from_cli: opts.fromCli,
    to_cli: opts.toCli,
    conversation_id: (opts.conversationId || from || '').trim(),
    mode: opts.mode || prefs.mode,
    token_budget: opts.tokenBudget ?? prefs.tokenBudget,
    import_session_id: opts.importSessionId || undefined,
    kind: opts.kind || 'cli',
    to_kind: opts.toKind,
    to_agent: opts.toAgent,
    to_label: opts.toLabel,
    from_label: opts.fromLabel,
    from_agent: opts.fromAgent,
  })
}


export interface CrossKindHopSpec {
  agentId: string
  conversationId: string
  fromCli: string
  toCli: string
  toKind: 'cli' | 'api' | 'remote'
  toAgent: string
  toLabel: string
  fromLabel?: string
}

/**
 * True when both ends name the same backend. `hop_backend` rejects that
 * (`from_cli` and `to_cli` must differ) before it writes a pending seed.
 * A CLI provider-profile pick is this case: the profile is only a banner
 * label, and posting the hop would 400 without changing the adapter.
 */
export function reconfigureHopIsIdentity(spec: { fromCli: string; toCli: string }): boolean {
  const from = spec.fromCli.trim().toLowerCase()
  const to = spec.toCli.trim().toLowerCase()
  return from.length > 0 && from === to
}

/**
 * #1436 / #1437 — a provider-profile pick reconfigures the current seat.
 * The hop kind is that seat (cli / remote / api), never a hardcoded `api`.
 * CLI destinations stay keyed by the current CLI; remote and api destinations
 * stay keyed by the seat record id. `profile` is only the banner label.
 * When `reconfigureHopIsIdentity` is true the caller shows the provider
 * notice instead of posting a hop the server will reject.
 */
export function reconfigureHopForSeat(input: {
  seatKind: 'api' | 'cli' | 'remote' | 'team'
  seatId: string
  conversationId: string
  profile: string
  currentCli?: string
  currentRemoteId?: string
}): CrossKindHopSpec {
  const hopKind: 'cli' | 'api' | 'remote' =
    input.seatKind === 'remote' ? 'remote' : input.seatKind === 'cli' ? 'cli' : 'api'
  const cliName = (input.currentCli || '').trim()
  const remoteId = (input.currentRemoteId || '').trim()
  const backendId =
    hopKind === 'cli' ? cliName || input.profile : hopKind === 'remote' ? remoteId || input.seatId : input.profile
  const fromCli =
    hopKind === 'cli' ? cliName || 'prior' : hopKind === 'remote' ? remoteId || 'prior' : 'api'
  return crossKindHopForReconfigure({
    seatId: input.seatId,
    conversationId: input.conversationId,
    fromCli,
    toCli: input.profile,
    toKind: hopKind,
    toBackendId: backendId,
  })
}

/**
 * #900 — turn a provider switch into a cross-kind hop: same conversation id,
 * the pending seed stored under the destination seat, CLI destinations keyed
 * by adapter name (prepare_cli_turn consumes by CLI), api/remote keyed by
 * seat record id (the consumer matches what the send frame resolves).
 */
export function crossKindHopForReconfigure(input: {
  /** Seat id of the agent being reconfigured (blueprint / remote:kind / team:id). */
  seatId: string
  conversationId: string
  /** Current backend label (grok, omb, auxiliary …). */
  fromCli: string
  /** Picked backend label. */
  toCli: string
  /** Destination seat kind. */
  toKind: 'cli' | 'api' | 'remote'
  /** Destination backend record id (cli catalog id, remote impl id). */
  toBackendId: string
}): CrossKindHopSpec {
  const seat = (input.seatId || '').trim() || 'cli_agent'
  return {
    agentId: seat,
    conversationId: (input.conversationId || '').trim(),
    fromCli: (input.fromCli || 'prior').trim() || 'prior',
    toCli: input.toKind === 'cli' ? (input.toBackendId || input.toCli).trim() : seat,
    toKind: input.toKind,
    toAgent: input.toKind === 'cli' ? (input.toBackendId || input.toCli).trim() : seat,
    toLabel: input.toCli,
    fromLabel: input.fromCli,
  }
}

export function dispatchCliSessionHopped(detail: {
  agentId: string
  conversationId: string
  status: string
  fromCli: string
  toCli: string
}): void {
  try {
    window.dispatchEvent(new CustomEvent(CLI_SESSION_HOPPED_EVENT, { detail }))
  } catch {
    /* tests / non-browser */
  }
}

export function hopContinueTargets(current: string, catalog: readonly string[]): string[] {
  const self = current.trim().toLowerCase()
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of catalog) {
    const name = raw.trim()
    if (!name || name.toLowerCase() === self || seen.has(name)) continue
    seen.add(name)
    out.push(name)
  }
  return out
}
