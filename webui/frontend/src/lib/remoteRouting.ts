/**
 * REQ-904 / #502 — the single decision point for the navbar remote picker.
 *
 * The picker's `onChange` used to fuse the doctrine's two axes in one inline
 * handler: a provider pick *also* navigated (`?remote=`) and *also* deleted
 * `session`. This helper separates them so the fusion cannot be re-implemented:
 *
 * | Axis | Question | Owner | May change |
 * |---|---|---|---|
 * | Identity | which agent am I talking to? | route/URL + session | thread, session, seat |
 * | Provider | which backend does this agent use? | persisted binding | nothing else |
 *
 * A `RoutingPathChange` with `changed === 'agent'` arriving while a remote
 * seat is **in the URL** is an identity change (the user is switching remote
 * seats) — navigate + reset. The same shape arriving while a *named agent* is
 | selected is a provider change — inert except for the binding.
 */
import type { AgentRemoteBinding } from './agentRemote'

export interface RemoteRoutingRow {
  id: string
  kind?: string
}

export interface RemoteRoutingInput {
  next: { agent: string; changed: string; model?: string | null }
  /** The agent whose provider is being configured — never the provider itself. */
  bindingAgentId: string
  /** Present only when the URL carries a remote *seat* (identity view). */
  remoteFromUrl?: string
  configured: readonly RemoteRoutingRow[]
}

export interface RemoteRoutingDecision {
  /** Persist the agent's provider binding (`null` clears it). */
  binding?: AgentRemoteBinding | null
  /** Write `?remote=` (identity navigation only). */
  setRemote?: string
  /** Write `?session=` (identity/session navigation only). */
  setSession?: string
  /** Delete `?session=` (identity navigation only). */
  deleteSession?: boolean
}

export function applyRemoteRoutingChange(input: RemoteRoutingInput): RemoteRoutingDecision {
  const { next, bindingAgentId, remoteFromUrl, configured } = input

  // Identity view: `?remote=` is in the URL, so the picker switches seats.
  // This is the *existing, correct* behaviour — preserved and pinned.
  if (remoteFromUrl) {
    const decision: RemoteRoutingDecision = { setRemote: next.agent }
    if (next.changed === 'model' && next.model) decision.setSession = next.model
    else if (next.changed === 'agent') decision.deleteSession = true
    return decision
  }

  // Provider view: a named agent's backend changed. Inert on the route —
  // stated affirmatively so a consumer cannot "default" into deleting it.
  if (next.changed === 'model' && next.model) {
    return { setSession: next.model, deleteSession: false }
  }

  const remote = configured.find((row) => row.id === next.agent)
  if (!bindingAgentId) return { deleteSession: false }
  if (!next.agent || !remote) return { binding: null, deleteSession: false }
  return { binding: { id: remote.id, kind: remote.kind || remote.id }, deleteSession: false }
}
