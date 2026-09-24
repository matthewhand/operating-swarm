/**
 * #1088 — Alt+Up / Alt+Down sequential rail navigation (Herdr parity).
 *
 * REQ-172's Alt+1..9 slot model collided with native browser tab switching
 * (Alt+1..8 switches tabs on Linux/Windows), so the slots are gone. The
 * navigable sequence is the rail's visual order: visible pins first, then
 * every row in the uncollapsed sections. Movement is sequential with
 * boundary clamping — no wrap, no spill arithmetic, no digit keys.
 */

import { chatHrefForRowId } from './agentNotifications'

export function isHerdrAgent(agent?: { id?: string; kind?: string | null } | null): boolean {
  if (!agent) return false
  return agent.kind === 'herdr' || String(agent.id).startsWith('herdr:')
}

/**
 * #543: a herdr seat is URL-addressable like every other kind — the agent
 * name rides the remote-harness `session` param, so `?remote=herdr&session=<agent>`
 * IS the conversation target. The `herdr:<name>` rail id stays the seat's
 * identity (pins/sections/hides); the URL is just where it lives when active.
 */
export function herdrChatHref(agentId: string): string {
  const name = agentId.startsWith('herdr:') ? agentId.slice('herdr:'.length) : agentId
  return `/chat?remote=herdr&session=${encodeURIComponent(name)}`
}

/**
 * Structural row shape for nav targeting — callers own their row types
 * (AgentSidebar uses TeamRoster/RemoteEntry), so these stay minimum-viable.
 */
export interface RailRow {
  kind: 'agent' | 'team' | 'remote'
  id: string
  agent?: { id: string; name?: string | null; kind?: string | null } | null
  team?: { id: string; name?: string | null } | null
  remote?: { id: string; label?: string | null } | null
}

export interface RailHotkeyTarget {
  id: string
  kind: 'pin' | 'agent' | 'team' | 'remote'
  href: string
  name: string
  isHerdr?: boolean
}

/** The rail's visual order: visible pins, then every row in section order. */
export function computeRailNavSequence({
  visiblePins,
  orderedRows,
}: {
  visiblePins: Array<{ id: string; name?: string | null; kind?: string }>
  orderedRows: RailRow[]
}): RailHotkeyTarget[] {
  const targets: RailHotkeyTarget[] = []

  for (const pin of visiblePins) {
    // #543: herdr seats chat like every other kind — the pin targets the
    // agent's own conversation, not the settings-adjacent members page.
    const herdr = isHerdrAgent(pin)
    targets.push({
      id: pin.id,
      kind: 'pin',
      name: pin.name || pin.id,
      isHerdr: herdr,
      href: herdr ? herdrChatHref(pin.id) : chatHrefForRowId(pin.id),
    })
  }

  for (const row of orderedRows) {
    if (row.kind === 'team' && row.team) {
      targets.push({
        id: row.id,
        kind: 'team',
        name: row.team.name || row.team.id,
        href: `/chat?team=${encodeURIComponent(row.team.id)}`,
      })
    } else if (row.kind === 'remote' && row.remote) {
      targets.push({
        id: row.id,
        kind: 'remote',
        name: row.remote.label || row.remote.id,
        href: `/chat?remote=${encodeURIComponent(row.remote.id)}`,
      })
    } else if (row.agent) {
      const herdr = isHerdrAgent(row.agent)
      targets.push({
        id: row.id,
        kind: 'agent',
        name: row.agent.name || row.agent.id,
        isHerdr: herdr,
        href: herdr
          ? herdrChatHref(row.agent.id)
          : `/chat?blueprint=${encodeURIComponent(row.agent.id)}`,
      })
    }
  }

  return targets
}

function paramsOf(searchOrHref: string): URLSearchParams {
  const q = searchOrHref.includes('?')
    ? searchOrHref.slice(searchOrHref.indexOf('?') + 1)
    : searchOrHref
  return new URLSearchParams(q)
}

/**
 * Index in the sequence of the row the URL currently points at, or -1 when
 * nothing matches (Alt+Down then starts from the top).
 */
export function activeRailNavIndex(
  seq: RailHotkeyTarget[],
  currentSearch: string,
): number {
  if (!currentSearch) return -1
  const cur = paramsOf(currentSearch)
  const curRemote = cur.get('remote')
  const curSession = cur.get('session')
  const curTeam = cur.get('team')
  const curBlueprint = cur.get('blueprint') || cur.get('agent')
  if (!curRemote && !curTeam && !curBlueprint) return -1

  for (let i = 0; i < seq.length; i++) {
    const t = paramsOf(seq[i].href)
    if (curRemote) {
      if (t.get('remote') !== curRemote) continue
      const tSession = t.get('session')
      if (tSession && curSession && tSession !== curSession) continue
      if (tSession && !curSession) continue
      return i
    }
    if (curTeam && t.get('team') === curTeam) return i
    if (curBlueprint && t.get('blueprint') === curBlueprint) return i
  }
  return -1
}

/**
 * The next/previous target with boundary clamping — never wraps, never
 * escapes the sequence. An unanchored index (-1) starts from the top.
 */
export function stepRailNav(
  seq: RailHotkeyTarget[],
  currentIdx: number,
  dir: 1 | -1,
): RailHotkeyTarget | null {
  if (seq.length === 0) return null
  const next =
    currentIdx < 0 ? 0 : Math.min(seq.length - 1, Math.max(0, currentIdx + dir))
  return seq[next] ?? null
}
