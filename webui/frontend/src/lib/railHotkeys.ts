/**
 * REQ-172: Alt+1–9 spill into top unpinned rail rows when favourites < 10.
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
 * Structural row shape for hotkey targeting — callers own their row types
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

export function computeRailHotkeyTargets({
  visiblePins,
  orderedRows,
}: {
  visiblePins: Array<{ id: string; name?: string | null; kind?: string }>
  orderedRows: RailRow[]
}): RailHotkeyTarget[] {
  const targets: RailHotkeyTarget[] = []

  // Up to 9 pins (1-indexed Alt+1..9)
  for (let i = 0; i < Math.min(visiblePins.length, 9); i++) {
    const pin = visiblePins[i]
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

  // Leftover Alt+N slots filled from top of unpinned orderedRows (in order)
  const remaining = 9 - targets.length
  for (let i = 0; i < Math.min(orderedRows.length, remaining); i++) {
    const row = orderedRows[i]
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
