/**
 * REQ-172: Alt+1–9 spill into top unpinned rail rows when favourites < 10.
 */

import type { Team, RemoteConnection } from './api'
import { chatHrefForRowId } from './agentNotifications'

export function isHerdrAgent(agent?: { id?: string; kind?: string } | null): boolean {
  if (!agent) return false
  return agent.kind === 'herdr' || String(agent.id).startsWith('herdr:')
}

export interface RailRow {
  kind: 'agent' | 'team' | 'remote'
  id: string
  agent?: any
  team?: Team
  remote?: RemoteConnection
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
    const herdr = isHerdrAgent(pin)
    targets.push({
      id: pin.id,
      kind: 'pin',
      name: pin.name || pin.id,
      isHerdr: herdr,
      href: herdr ? '/teams/#herdr-members' : chatHrefForRowId(pin.id),
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
          ? '/teams/#herdr-members'
          : `/chat?blueprint=${encodeURIComponent(row.agent.id)}`,
      })
    }
  }

  return targets
}
