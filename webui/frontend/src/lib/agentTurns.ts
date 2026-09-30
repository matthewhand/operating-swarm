/**
 * ADR-017 PR-2 — the SPA-side turn registry.
 *
 * The server bookends every turn with `turn_started` / `turn_finished`
 * frames carrying `turn_id` + `agent_id` (#1113). This module is the pure
 * state layer:
 *
 * - `applyTurnFrame` folds a bookend into a snapshot (`turnId` → entry),
 *   so the UI can answer "which turn is this agent running right now?"
 * - `activeTurnFor` returns the live turn for an agent (insertion order —
 *   the server serialises turns per agent, so the latest entry wins).
 * - `stopLabelFor` names the button's contract: interrupt *that* turn.
 *
 * #1684 adds the *turn phase*: `AgentTurn.activeTool` is the tool call
 * currently in flight on that turn, folded from the live `tool_status`
 * frames the server already emits (`core/turn_phase.py`). It exists here
 * rather than on the message row for two reasons that both matter:
 *
 * 1. `docs/UI_DESIGN.md` §3 — the "Running" badge means *a tool call is in
 *    flight*, which is NOT the same state as the avatar's eye-dots ("waiting
 *    on a model response"). Mounting the badge off `isStreaming` is the bug
 *    that rule exists to prevent. The badge reads this field and only this
 *    field.
 * 2. The whole-SPA mux tap below is conversation-blind: an agent running in
 *    a chat you navigated away from still gets its phase recorded, so its
 *    rail/header chrome stays truthful.
 *
 * Three independent layers keep a badge from sticking on:
 *   1. the server emits a terminal `tool_status` before the turn ends;
 *   2. the `turn_finished` arm here clears `activeTool` unconditionally;
 *   3. `TOOL_STATUS_WATCHDOG_MS` bounds how long a badge can survive a
 *      socket that dies mid-tool. A badge that sticks on is worse than no
 *      badge, so the bound is deliberately the *cheapest* thing to lose.
 *
 * Display is intentionally not part of this module — bookends and tool
 * phases are protocol, not transcript. The working row reads the registry
 * only to scope its stop button and its badge.
 */

import { useEffect, useState } from 'react'
import { onSpaFrame } from './spaSocket'

/** A tool call currently in flight on a turn. */
export interface ActiveTool {
  /** The frame's opaque `id` (same key `ToolCallState` upserts on). */
  toolId: string
  /** The name the model saw — what the badge puts on screen. */
  name: string
}

export interface AgentTurn {
  turnId: string
  agentId: string
  state: 'running' | 'finished'
  /**
   * #1684: the tool call in flight on THIS turn, or `null`. Never derived
   * from transcript `streaming` — that flag means "waiting on a model
   * response" and is what animates the avatar's eye-dots.
   */
  activeTool: ActiveTool | null
}

export type TurnSnapshot = Record<string, AgentTurn>

export interface TurnBookendFrame {
  kind: 'turn_started' | 'turn_finished'
  turnId: string
  agentId: string
}

/**
 * #1684 — the turn-phase frame, shaped exactly like the parsed
 * `ChatWsEvent` of kind `tool_status` so it can be fed in verbatim.
 *
 * `turnId` is accepted but **not sent** by the live producer: the frame the
 * server builds carries `{type, id, name, status, agent_id}` only
 * (`swarm.tool_executor.emit_tool_status`), and demo replay
 * (`swarm/demo/scenarios.py`) omits nothing else either. The reducer
 * therefore resolves the target turn by `agentId` and must never assume a
 * `turnId` is present.
 */
export interface ToolPhaseFrame {
  kind: 'tool_status'
  id: string
  name: string
  status: string
  agentId?: string
  turnId?: string
}

export type TurnFrame = TurnBookendFrame | ToolPhaseFrame

/**
 * #1684: how long a badge may survive without a terminal frame.
 *
 * Derived from the server, not guessed: `elicit_tool_approval` waits up to
 * 300s for a human decision (`consumers.py`), so a tool call can legitimately
 * stay in flight that long and the bound must clear it. The turn itself is
 * bounded at 600s (`core/agent_run_timeout.DEFAULT_AGENT_RUN_TIMEOUT_S`), so
 * this expires well before a wedged turn is ever declared dead server-side.
 */
export const TOOL_STATUS_WATCHDOG_MS = 330_000

/** Statuses that end a tool call. `allowed` is NOT terminal: the call runs. */
const TERMINAL_TOOL_STATUSES = new Set(['done', 'error', 'denied'])

export const AGENT_TURNS_EVENT = 'swarm:agent-turns'

let globalTurns: TurnSnapshot = {}
const listeners = new Set<(snapshot: TurnSnapshot) => void>()

interface ArmedWatchdog {
  toolId: string
  timer: ReturnType<typeof setTimeout>
}

/** turnId → the bound that expires a badge its socket never finished. */
const toolWatchdogs = new Map<string, ArmedWatchdog>()

function notifyListeners(): void {
  for (const listener of listeners) {
    try {
      listener(globalTurns)
    } catch {
      /* ignore listener errors */
    }
  }
  if (typeof window !== 'undefined' && window.dispatchEvent) {
    try {
      window.dispatchEvent(
        new CustomEvent(AGENT_TURNS_EVENT, { detail: globalTurns }),
      )
    } catch {
      /* window unavailable */
    }
  }
}

export function getTurnSnapshot(): TurnSnapshot {
  return globalTurns
}

export function resetTurnRegistry(): void {
  for (const armed of toolWatchdogs.values()) clearTimeout(armed.timer)
  toolWatchdogs.clear()
  globalTurns = {}
  notifyListeners()
}

/**
 * The id spellings a lookup accepts: the literal one, and the unscoped one
 * for `agent:` / `blueprint:` / `team:` / `remote:` prefixed callers. One
 * rule, shared by `isAgentTurnActive` and the tool-phase lookup, so a badge
 * can never resolve an agent differently than the row that owns it.
 */
function agentIdCandidates(agentId?: string | null): string[] {
  if (!agentId) return []
  const stripped = agentId.replace(/^(team|remote|agent|blueprint):/, '')
  return stripped === agentId ? [agentId] : [agentId, stripped]
}

function runningTurnIdFor(snapshot: TurnSnapshot, agentIds: string[]): string | null {
  if (agentIds.length === 0) return null
  let found: string | null = null
  for (const turn of Object.values(snapshot)) {
    if (turn.state === 'running' && agentIds.includes(turn.agentId)) found = turn.turnId
  }
  return found
}

/**
 * #1684: fold one `tool_status` into the registry.
 *
 * Target resolution, in order: an explicit `turnId` that is still running,
 * then the agent's newest running turn. There is no third fallback and in
 * particular **no turn is invented** — a frame that cannot be attributed to a
 * live turn is dropped, because a phantom turn would animate avatars and
 * could never be finished.
 */
export function reduceToolPhaseFrame(
  prev: TurnSnapshot,
  frame: ToolPhaseFrame,
): TurnSnapshot {
  const targetId =
    (frame.turnId && prev[frame.turnId]?.state === 'running' ? frame.turnId : null) ??
    runningTurnIdFor(prev, agentIdCandidates(frame.agentId))
  if (targetId === null) return prev
  const turn = prev[targetId]
  if (TERMINAL_TOOL_STATUSES.has(frame.status)) {
    // Id-exact correlation: the live producer mints one id per invocation and
    // reuses it on the terminal frame (`turn_phase.py`'s in-flight map), so a
    // terminal frame for some *other* call must not retire this one. Anything
    // it misses is caught by `turn_finished` or the watchdog.
    if (!turn.activeTool || turn.activeTool.toolId !== frame.id) return prev
    return { ...prev, [targetId]: { ...turn, activeTool: null } }
  }
  // `allowed` (and anything unknown) is a non-terminal phase: the call is
  // approved and about to execute, so the badge stays. The live producers
  // always send `running` first, so there is no path where a tool is in
  // flight but only ever announced as `allowed`.
  if (frame.status !== 'running') return prev
  const activeTool: ActiveTool = { toolId: frame.id, name: frame.name }
  if (
    turn.activeTool?.toolId === activeTool.toolId &&
    turn.activeTool.name === activeTool.name
  ) {
    return prev
  }
  return { ...prev, [targetId]: { ...turn, activeTool } }
}

function reduceToolCleared(prev: TurnSnapshot, turnId: string): TurnSnapshot {
  const turn = prev[turnId]
  if (!turn?.activeTool) return prev
  return { ...prev, [turnId]: { ...turn, activeTool: null } }
}

/**
 * #1684: the client watchdog (never-stuck layer 3). Armed per *tool*, not per
 * turn, and only re-armed when the in-flight tool actually changes, so a long
 * turn running many tools in a row does not keep one call's badge alive.
 */
function syncToolWatchdogs(next: TurnSnapshot): void {
  for (const turn of Object.values(next)) {
    const armed = toolWatchdogs.get(turn.turnId)
    if (turn.activeTool) {
      if (armed && armed.toolId === turn.activeTool.toolId) continue
      if (armed) clearTimeout(armed.timer)
      const turnId = turn.turnId
      toolWatchdogs.set(turnId, {
        toolId: turn.activeTool.toolId,
        timer: setTimeout(() => {
          toolWatchdogs.delete(turnId)
          recordToolCleared(turnId)
        }, TOOL_STATUS_WATCHDOG_MS),
      })
      continue
    }
    if (armed) {
      clearTimeout(armed.timer)
      toolWatchdogs.delete(turn.turnId)
    }
  }
}

export function reduceTurnFrame(prev: TurnSnapshot, frame: TurnFrame): TurnSnapshot {
  if (frame.kind === 'tool_status') return reduceToolPhaseFrame(prev, frame)
  if (frame.kind === 'turn_started') {
    // Idempotent: a re-delivered bookend must not wipe a tool that is in
    // flight right now (the registry is fed by two taps, see `useAgentTurns`).
    const existing = prev[frame.turnId]
    if (existing && existing.state === 'running' && existing.agentId === frame.agentId) {
      return prev
    }
    return {
      ...prev,
      [frame.turnId]: {
        turnId: frame.turnId,
        agentId: frame.agentId,
        state: 'running',
        activeTool: null,
      },
    }
  }
  const existing = prev[frame.turnId]
  if (!existing) return prev
  // #1684: never-stuck layer 2. `turn_finished` is the one frame that is
  // guaranteed for every turn, so it retires the badge regardless of whether
  // the tool's own terminal frame made it back.
  if (existing.state === 'finished' && !existing.activeTool) return prev
  return {
    ...prev,
    [frame.turnId]: { ...existing, state: 'finished', activeTool: null },
  }
}

export function recordTurnFrame(frame: TurnFrame): TurnSnapshot {
  const next = reduceTurnFrame(globalTurns, frame)
  syncToolWatchdogs(next)
  if (next === globalTurns) return globalTurns
  globalTurns = next
  notifyListeners()
  return globalTurns
}

/** #1684: the turn-phase recorder, beside `recordTurnFrame` for bookends. */
export function recordToolPhaseFrame(frame: ToolPhaseFrame): TurnSnapshot {
  return recordTurnFrame(frame)
}

function recordToolCleared(turnId: string): void {
  const next = reduceToolCleared(globalTurns, turnId)
  if (next === globalTurns) return
  globalTurns = next
  notifyListeners()
}

export function applyTurnFrame(prev: TurnSnapshot, frame: TurnFrame): TurnSnapshot
export function applyTurnFrame(frame: TurnFrame): TurnSnapshot
export function applyTurnFrame(
  prevOrFrame: TurnSnapshot | TurnFrame,
  maybeFrame?: TurnFrame,
): TurnSnapshot {
  if (maybeFrame) {
    return reduceTurnFrame(prevOrFrame as TurnSnapshot, maybeFrame)
  }
  return recordTurnFrame(prevOrFrame as TurnFrame)
}

/** Every live (running) turn in insertion order. */
export function runningTurns(snapshot: TurnSnapshot): AgentTurn[] {
  return Object.values(snapshot).filter((turn) => turn.state === 'running')
}

/** The live (running) turn an agent owns, if any. Last one wins. */
export function activeTurnFor(
  snapshot: TurnSnapshot,
  agentId: string,
): AgentTurn | null {
  let found: AgentTurn | null = null
  for (const turn of Object.values(snapshot)) {
    if (turn.state === 'running' && turn.agentId === agentId) found = turn
  }
  return found
}

/** True when the agent has any turn in 'running' state in the given or global snapshot. */
export function isAgentTurnActive(
  agentId?: string | null,
  snapshot: TurnSnapshot = globalTurns,
): boolean {
  if (!agentId) return false
  return runningTurnIdFor(snapshot, agentIdCandidates(agentId)) !== null
}

/**
 * #1684: the tool call in flight on the agent's live turn, or `null`.
 *
 * Resolved through the same candidate list as `isAgentTurnActive`, so one
 * busy agent can never badge another and a prefixed id resolves identically
 * for the avatar, the badge, and the rail. A CLI/remote seat emits no
 * `tool_status` at all, so this correctly stays `null` there — the badge must
 * never be faked from `streaming`.
 */
export function activeToolFor(
  snapshot: TurnSnapshot,
  agentId?: string | null,
): ActiveTool | null {
  const candidates = agentIdCandidates(agentId)
  if (candidates.length === 0) return null
  let found: ActiveTool | null = null
  for (const turn of Object.values(snapshot)) {
    if (turn.state !== 'running' || !candidates.includes(turn.agentId)) continue
    if (turn.activeTool) found = turn.activeTool
  }
  return found
}

/** Subscribe to live turn changes. Returns unsubscribe callback. */
export function subscribeAgentTurns(
  handler: (snapshot: TurnSnapshot) => void,
): () => void {
  listeners.add(handler)
  return () => {
    listeners.delete(handler)
  }
}

/** Reactive hook to read the global turn registry. */
export function useAgentTurns(): TurnSnapshot {
  const [snapshot, setSnapshot] = useState<TurnSnapshot>(() => getTurnSnapshot())
  useEffect(() => {
    // #1118: fold every conversation's bookends from the whole-SPA mux tap.
    // Once you click away from a chat its per-conversation listener is gone,
    // but the sticky server session keeps sending over the one socket and the
    // conversation-blind tap still sees those frames. Without this, a
    // background agent's turn can never animate its rail/header avatar.
    // #1684: `tool_status` rides the same tap — it is how a background
    // agent's Running badge keeps telling the truth after you navigate away.
    const tap = onSpaFrame((event) => {
      if (event.kind === 'turn_started' || event.kind === 'turn_finished') {
        recordTurnFrame(event)
        return
      }
      if (event.kind === 'tool_status') {
        recordToolPhaseFrame(event)
      }
    })
    setSnapshot(getTurnSnapshot())
    const unsubscribe = subscribeAgentTurns((next) => setSnapshot(next))
    return () => {
      tap.release()
      unsubscribe()
    }
  }, [])
  return snapshot
}

/** Reactive hook to check if a specific agent currently has a live turn. */
export function useAgentTurnActive(agentId?: string | null): boolean {
  const turns = useAgentTurns()
  return isAgentTurnActive(agentId, turns)
}

/**
 * #1684: the agent's in-flight tool, reactively. This is the badge's only
 * input — see `docs/UI_DESIGN.md` §3 for why it must not be the `streaming`
 * flag the avatar eye-dots already use.
 */
export function useActiveToolForAgent(agentId?: string | null): ActiveTool | null {
  const turns = useAgentTurns()
  return activeToolFor(turns, agentId)
}

/** Copy for the row stop: it stops THIS turn, not the agent's whole queue. */
export function stopLabelFor(turn: AgentTurn | null): string {
  return turn
    ? `Stop this agent's generation (other turns keep running)`
    : `Stop generating`
}
