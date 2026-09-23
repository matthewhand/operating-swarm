// #856 slice 11: rail context-menu / section / notification command surface
// moved verbatim from AgentSidebar (menu close, section rename/create/move/
// delete/talk-lock, move-to-section, per-agent bubble-theme override, pane
// menu, notification toggle + permission retry). Menu states stay
// page-owned; this hook owns the commands that act on them.
import { useCallback, type Dispatch, type SetStateAction } from 'react'
import {
  setAgentBubbleTheme,
  type BubbleTheme,
} from '../../lib/bubbleTheme'
import {
  isAgentNotifyEnabled,
  disableAgentNotify,
  enableAgentNotifications,
} from '../../lib/agentNotifications'
import {
  NEW_SECTION_TARGET,
  createSection,
  createSectionWithAgent,
  deleteSection,
  isUnassignedSection,
  moveAgentToSection,
  moveSection,
  renameSection,
  type RailSectionsState,
  toggleSectionInternalOnly,
} from '../../lib/railSections'
import { unpinAgent, type PinnedAgent } from '../../lib/pinnedAgents'
import type { RailMenuItemId } from '../../lib/railContextMenu'
import type {
  ContextMenuState,
  NotifyOutcomeHint,
  SectionMenuState,
} from './rows'

export interface RailMenuCommandsOptions {
  menu: ContextMenuState | null
  sectionMenu: SectionMenuState | null
  paneMenu: { x: number; y: number } | null
  sectionState: RailSectionsState
  editingSectionId: string | null
  editingSectionName: string
  notifyIds: string[]
  notifyHint: NotifyOutcomeHint | null
  isPinnedId: (id: string | null | undefined) => boolean
  setMenu: Dispatch<SetStateAction<ContextMenuState | null>>
  setSectionMenu: Dispatch<SetStateAction<SectionMenuState | null>>
  setPaneMenu: Dispatch<SetStateAction<{ x: number; y: number } | null>>
  setSectionState: Dispatch<SetStateAction<RailSectionsState>>
  setEditingSectionId: Dispatch<SetStateAction<string | null>>
  setEditingSectionName: Dispatch<SetStateAction<string>>
  setPins: Dispatch<SetStateAction<PinnedAgent[]>>
  setNotifyIds: Dispatch<SetStateAction<string[]>>
  setNotifyHint: Dispatch<SetStateAction<NotifyOutcomeHint | null>>
}

export function useRailMenuCommands(opts: RailMenuCommandsOptions) {
  const {
    menu: _menu,
    sectionMenu,
    sectionState,
    editingSectionId,
    editingSectionName,
    notifyIds,
    notifyHint,
    isPinnedId,
    setMenu,
    setSectionMenu,
    setPaneMenu,
    setSectionState,
    setEditingSectionId,
    setEditingSectionName,
    setPins,
    setNotifyIds,
    setNotifyHint,
  } = opts
  void _menu

  const closeMenu = useCallback(() => {
    setMenu(null)
    setSectionMenu(null)
    setPaneMenu(null)
  }, [setMenu, setSectionMenu, setPaneMenu])

  const commitSectionRename = useCallback(() => {
    if (!editingSectionId) return
    setSectionState((current) => renameSection(current, editingSectionId, editingSectionName))
    setEditingSectionId(null)
    setEditingSectionName('')
  }, [editingSectionId, editingSectionName])

  const cancelSectionRename = useCallback(() => {
    setEditingSectionId(null)
    setEditingSectionName('')
  }, [setEditingSectionId, setEditingSectionName])

  const startSectionRename = useCallback((sectionId: string, name: string) => {
    setEditingSectionId(sectionId)
    setEditingSectionName(name)
    setSectionMenu(null)
  }, [setEditingSectionId, setEditingSectionName, setSectionMenu])

  const handleMoveTo = useCallback(
    (agentId: string, target: string) => {
      if (!agentId) return
      // #801: a pinned agent moved to a section must LEAVE the pin grid —
      // excludePinnedFromList strips pinned ids from the section lists, so
      // keeping the pin would park the agent in limbo (membership set, row
      // rendered nowhere). Unpinning matches drag-to-section behavior.
      const wasPinned = isPinnedId(agentId)
      if (wasPinned) {
        setPins((current) =>
          current.some((pin) => pin.id === agentId) ? unpinAgent(agentId, current) : current,
        )
      }
      if (target === NEW_SECTION_TARGET) {
        const created = createSectionWithAgent(sectionState, agentId)
        setSectionState(created.state)
        startSectionRename(created.section.id, created.section.name)
        closeMenu()
        return
      }
      setSectionState((current) => moveAgentToSection(current, agentId, target))
      closeMenu()
    },
    [closeMenu, isPinnedId, sectionState, setPins, setSectionState, startSectionRename],
  )

  /** #724: dispatch the per-agent bubble-theme override from the rail menu. */
  const handleBubbleTheme = useCallback(
    (agentId: string, theme: string) => {
      if (!agentId) return
      setAgentBubbleTheme(agentId, theme === '__default__' ? null : (theme as BubbleTheme))
      closeMenu()
    },
    [closeMenu],
  )

  const openSectionMenuAt = useCallback(
    (sectionId: string, sectionName: string, clientX: number, clientY: number) => {
      if (isUnassignedSection(sectionId)) return
      const pad = 8
      const width = 200
      const height = 220
      const x = Math.min(clientX, window.innerWidth - width - pad)
      const y = Math.min(clientY, window.innerHeight - height - pad)
      setMenu(null)
      setSectionMenu({
        sectionId,
        sectionName,
        x: Math.max(pad, x),
        y: Math.max(pad, y),
      })
    },
    [setMenu, setSectionMenu],
  )

  const handleSectionMenuSelect = useCallback(
    (id: RailMenuItemId) => {
      if (!sectionMenu) return
      const { sectionId, sectionName } = sectionMenu
      if (id === 'section-create') {
        const created = createSection(sectionState)
        setSectionState(created.state)
        closeMenu()
        startSectionRename(created.section.id, created.section.name)
        return
      }
      if (id === 'section-rename') {
        startSectionRename(sectionId, sectionName)
        return
      }
      if (id === 'section-talk-lock') {
        setSectionState((current) => toggleSectionInternalOnly(current, sectionId))
        closeMenu()
        return
      }
      if (id === 'section-move-up') {
        setSectionState((current) => moveSection(current, sectionId, 'up'))
        closeMenu()
        return
      }
      if (id === 'section-move-down') {
        setSectionState((current) => moveSection(current, sectionId, 'down'))
        closeMenu()
        return
      }
      if (id === 'section-delete') {
        setSectionState((current) => deleteSection(current, sectionId))
        if (editingSectionId === sectionId) cancelSectionRename()
        closeMenu()
      }
    },
    [
      cancelSectionRename,
      closeMenu,
      editingSectionId,
      sectionMenu,
      sectionState,
      setSectionState,
      startSectionRename,
    ],
  )

  // #172: right-click the rail background to create a fresh empty section.
  // Drag any agent/pin onto its header to move it in (dropOnSection accepts
  // both rows and pinned ids), so sections can group a "locked comms" roster.
  const openPaneMenuAt = useCallback((clientX: number, clientY: number) => {
    const pad = 8
    const width = 200
    const height = 160
    const x = Math.min(clientX, window.innerWidth - width - pad)
    const y = Math.min(clientY, window.innerHeight - height - pad)
    setMenu(null)
    setSectionMenu(null)
    setPaneMenu({ x: Math.max(pad, x), y: Math.max(pad, y) })
  }, [setMenu, setSectionMenu, setPaneMenu])

  const handlePaneMenuSelect = useCallback(
    (id: RailMenuItemId) => {
      if (id !== 'section-create') return
      const created = createSection(sectionState)
      setSectionState(created.state)
      closeMenu()
      startSectionRename(created.section.id, created.section.name)
    },
    [closeMenu, sectionState, setSectionState, startSectionRename],
  )

  const toggleNotify = useCallback(
    async (agentId: string) => {
      if (!agentId) {
        closeMenu()
        return
      }
      if (isAgentNotifyEnabled(agentId, notifyIds)) {
        setNotifyIds(disableAgentNotify(agentId, notifyIds))
        closeMenu()
        return
      }
      const result = await enableAgentNotifications(agentId)
      setNotifyIds(result.ids)
      closeMenu()
      if (result.outcome !== 'granted') {
        setNotifyHint({
          agentId,
          outcome: result.outcome,
          requestFailed: result.requestFailed,
        })
      }
    },
    [closeMenu, notifyIds, setNotifyHint, setNotifyIds],
  )

  /** #546: re-ask. `never-asked` means the prompt did not appear, so it is worth
   *  another attempt rather than a dead-end sentence. */
  const retryNotifyPermission = useCallback(async () => {
    if (!notifyHint) return
    const result = await enableAgentNotifications(notifyHint.agentId)
    setNotifyIds(result.ids)
    if (result.outcome === 'granted') {
      setNotifyHint(null)
      return
    }
    setNotifyHint({
      agentId: notifyHint.agentId,
      outcome: result.outcome,
      requestFailed: result.requestFailed,
    })
  }, [notifyHint, setNotifyHint, setNotifyIds])

  return {
    closeMenu,
    commitSectionRename,
    cancelSectionRename,
    startSectionRename,
    handleMoveTo,
    handleBubbleTheme,
    openSectionMenuAt,
    handleSectionMenuSelect,
    openPaneMenuAt,
    handlePaneMenuSelect,
    toggleNotify,
    retryNotifyPermission,
  }
}
