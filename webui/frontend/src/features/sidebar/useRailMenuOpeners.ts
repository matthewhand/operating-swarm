// #856 slice 13: rail menu-opener surface moved verbatim from AgentSidebar —
// resolveMenuKind, openMenuAt (with the CLI run-status probe), the long-press
// timer helper, rowMenuHandlers (contextmenu / keyboard / touch), and the
// definition + agent-settings openers. The menu state stays page-owned.
import {
  isCliRailAgent,
  isHerdrAgent,
  type SidebarAgent,
} from './rows'
import { fetchCliRunStatus } from '../../lib/api/settings'
import { isRailMenuKey, type RailMenuKind } from '../../lib/railContextMenu'
import type { ContextMenuState, SectionMenuState } from './rows'
import { openSettingsSheet } from '../../components/SettingsSheet'
import { openAgentEditor } from '../../lib/agentSettings'
import {
  RAIL_LONG_PRESS_MS,
} from '../../lib/railContextMenu'
import type {
  KeyboardEvent as ReactKeyboardEvent,
  MouseEvent as ReactMouseEvent,
  TouchEvent as ReactTouchEvent,
} from 'react'
import type { MemberSession } from '../../lib/sessionPicker'
import type { Dispatch, SetStateAction } from 'react'

export interface RailMenuOpenerOptions {
  agents: SidebarAgent[]
  searchParams: URLSearchParams
  pins: { id: string }[]
  longPressRef: { current: { timer: number | null; opened: boolean } }
  setMenu: Dispatch<SetStateAction<ContextMenuState | null>>
  setSectionMenu: Dispatch<SetStateAction<SectionMenuState | null>>
  setCliRunningIds: Dispatch<SetStateAction<Set<string>>>
  onClose?: () => void
  closeMenu: () => void
}

export function useRailMenuOpeners(opts: RailMenuOpenerOptions) {
  const {
    agents,
    searchParams,
    pins,
    longPressRef,
    setMenu,
    setSectionMenu,
    setCliRunningIds,
    onClose,
    closeMenu,
  } = opts

  const resolveMenuKind = (hideId: string, hinted?: RailMenuKind): RailMenuKind => {
    if (hinted) return hinted
    if (hideId.startsWith('team:')) return 'team'
    if (hideId.startsWith('remote:')) return 'remote'
    const agent = agents.find((row) => row.id === hideId)
    if (agent && isCliRailAgent(agent)) return 'cli'
    // #543: herdr rows get their own menu kind — no Edit/Duplicate (no
    // swarm-owned profile), no swarm conversation id, matching 'remote'.
    if (agent && isHerdrAgent(agent)) return 'herdr'
    if ((agent as unknown as { kind?: string })?.kind === 'blueprint') return 'blueprint'
    return 'api'
  }

  const openMenuAt = (
    clientX: number,
    clientY: number,
    hideId: string,
    label: string,
    hidden: boolean,
    kind?: RailMenuKind,
    sessions?: MemberSession[],
    entityId?: string,
  ) => {
    const pad = 8
    const width = 220
    const height = 320
    const x = Math.min(clientX, window.innerWidth - width - pad)
    const y = Math.min(clientY, window.innerHeight - height - pad)
    const resolvedKind = resolveMenuKind(hideId, kind)
    const row = agents.find((agent) => agent.id === hideId)
    const isCli = resolvedKind === 'cli' || Boolean(row && isCliRailAgent(row))
    const cliFromUrl = searchParams.get('cli') || ''
    const cliName = (isCli && (cliFromUrl || row?.cli)) || ''
    setSectionMenu(null)
    setMenu({
      agentId: hideId,
      agentName: label,
      hidden,
      pinned: pins.some((pin) => pin.id === hideId),
      x: Math.max(pad, x),
      y: Math.max(pad, y),
      kind: resolvedKind,
      entityId: entityId || hideId,
      sessions,
      isCli,
      cli: cliName,
    })
    if (isCli) {
      void fetchCliRunStatus(hideId)
        .then((status) => {
          setCliRunningIds((current) => {
            const next = new Set(current)
            if (status.running) next.add(hideId)
            else next.delete(hideId)
            return next
          })
        })
        .catch(() => {
          /* keep event-sourced state */
        })
    }
  }

  const clearLongPress = () => {
    if (longPressRef.current.timer != null) {
      window.clearTimeout(longPressRef.current.timer)
      longPressRef.current.timer = null
    }
  }

  const rowMenuHandlers = (
    hideId: string,
    label: string,
    hidden: boolean,
    kind?: RailMenuKind,
    sessions?: MemberSession[],
    entityId?: string,
  ) => ({
    onContextMenu: (event: ReactMouseEvent) => {
      event.preventDefault()
      openMenuAt(event.clientX, event.clientY, hideId, label, hidden, kind, sessions, entityId)
    },
    onKeyDown: (event: ReactKeyboardEvent<HTMLElement>) => {
      if (!isRailMenuKey(event)) return
      event.preventDefault()
      const rect = event.currentTarget.getBoundingClientRect()
      openMenuAt(rect.left + 12, rect.bottom, hideId, label, hidden, kind, sessions, entityId)
    },
    onTouchStart: (event: ReactTouchEvent<HTMLElement>) => {
      const touch = event.touches[0]
      if (!touch) return
      longPressRef.current.opened = false
      clearLongPress()
      longPressRef.current.timer = window.setTimeout(() => {
        longPressRef.current.opened = true
        openMenuAt(touch.clientX, touch.clientY, hideId, label, hidden, kind, sessions, entityId)
      }, RAIL_LONG_PRESS_MS)
    },
    onTouchEnd: (event: ReactTouchEvent<HTMLElement>) => {
      clearLongPress()
      if (longPressRef.current.opened) {
        event.preventDefault()
      }
    },
    onTouchMove: () => {
      clearLongPress()
    },
  })

  const openDefinition = (
    kind: 'role' | 'blueprint' | 'team',
    id: string,
    extras?: { blueprintId?: string; teamId?: string },
  ) => {
    openSettingsSheet({
      section: 'definition',
      definitionKind: kind,
      definitionId: id,
      blueprintId: extras?.blueprintId,
      teamId: extras?.teamId,
    })
    onClose?.()
  }

  const openAgentSettings = (agent: { id: string; name: string }) => {
    openAgentEditor({ agentId: agent.id, agentName: agent.name })
    closeMenu()
    onClose?.()
  }

  return {
    resolveMenuKind,
    openMenuAt,
    clearLongPress,
    rowMenuHandlers,
    openDefinition,
    openAgentSettings,
  }
}
