// #856 slice 12: rail drag-drop / pin / hide interaction surface moved
// verbatim from AgentSidebar — finishDrag with the #725 global drag-end
// safety net, hide/unhide, pin toggle, pin-grid drops, row reorder drops
// (#761 relative placement + section assignment), section drops, and
// row-drag begin. Drag/pin/hide states stay page-owned.
import { useCallback, useEffect, type Dispatch, type DragEvent as ReactDragEvent, type SetStateAction } from 'react'
import {
  canHideAgent,
  hideAgentId,
  unhideAgentId,
} from '../../lib/hiddenAgents'
import {
  beginRailDrag,
  dropHalfFromClientY,
  endRailDrag,
  peekRailDrag,
} from '../../lib/railOrder'
import {
  endAgentDrag,
  movePinnedAgent,
  parseAgentDragPayload,
  pinAgent,
  unpinAgent,
  writeAgentDragPayload,
  type PinnedAgent,
} from '../../lib/pinnedAgents'
import {
  moveAgentToSection,
  sectionIdForAgent,
  type RailSectionsState,
} from '../../lib/railSections'

export interface RailDragCommandsOptions {
  draggingId: string | null
  resolvedHiddenIds: string[]
  sectionState: RailSectionsState
  isPinnedId: (id: string | null | undefined) => boolean
  reorderBefore: (fromId: string, beforeId: string) => void
  reorderAfter: (fromId: string, afterId: string) => void
  closeMenu: () => void
  setDraggingId: Dispatch<SetStateAction<string | null>>
  setDropTargetId: Dispatch<SetStateAction<string | null>>
  setSectionDropId: Dispatch<SetStateAction<string | null>>
  setDropActive: Dispatch<SetStateAction<boolean>>
  setListDropActive: Dispatch<SetStateAction<boolean>>
  setHideDropActive: Dispatch<SetStateAction<boolean>>
  setBinDragOver: Dispatch<SetStateAction<boolean>>
  setPins: Dispatch<SetStateAction<PinnedAgent[]>>
  setHiddenIds: Dispatch<SetStateAction<string[] | null>>
  setSectionState: Dispatch<SetStateAction<RailSectionsState>>
  hideDropDepth: { current: number }
}

export function useRailDragCommands(opts: RailDragCommandsOptions) {
  const {
    draggingId,
    resolvedHiddenIds,
    sectionState,
    isPinnedId,
    reorderBefore,
    reorderAfter,
    closeMenu,
    setDraggingId,
    setDropTargetId,
    setSectionDropId,
    setDropActive,
    setListDropActive,
    setHideDropActive,
    setBinDragOver,
    setPins,
    setHiddenIds,
    setSectionState,
    hideDropDepth,
  } = opts

  const finishDrag = useCallback(() => {
    endAgentDrag()
    endRailDrag()
    setDraggingId(null)
    setDropTargetId(null)
    setSectionDropId(null)
    setDropActive(false)
    setListDropActive(false)
    setHideDropActive(false)
    setBinDragOver(false)
    hideDropDepth.current = 0
  }, [setDraggingId, setDropTargetId, setSectionDropId, setDropActive, setListDropActive, setHideDropActive, setBinDragOver, hideDropDepth])

  // #725: global safety net — if the browser never delivers `onDragEnd` to the
  // React element (pointer left the window, OS cancelled the drag, or a
  // re-render during a 429 storm orphaned the handler) draggingId would stay
  // set forever. The window-level listener catches it regardless of source.
  useEffect(() => {
    if (!draggingId) return
    const onGlobalDragEnd = () => finishDrag()
    const onVisibilityHide = () => { if (document.visibilityState === 'hidden') finishDrag() }
    window.addEventListener('dragend', onGlobalDragEnd)
    document.addEventListener('visibilitychange', onVisibilityHide)
    return () => {
      window.removeEventListener('dragend', onGlobalDragEnd)
      document.removeEventListener('visibilitychange', onVisibilityHide)
    }
  }, [draggingId, finishDrag])

  /**
   * Hide conceals the id from the conversation list and the visible favourite
   * grid. The pin stays in swarm_pinned_agents so Unhide restores the same
   * favourite slot. Role agents (support, gate, skeptic) are not exempt.
   */
  const hideFromRail = useCallback(
    (id: string) => {
      if (!id || !canHideAgent(id)) return
      setHiddenIds((current) => hideAgentId(id, current ?? resolvedHiddenIds))
    },
    [resolvedHiddenIds, setHiddenIds],
  )

  const hideAgent = useCallback(
    (id: string) => {
      hideFromRail(id)
      closeMenu()
    },
    [closeMenu, hideFromRail],
  )

  const unhideAgent = useCallback(
    (id: string) => {
      setHiddenIds((current) => unhideAgentId(id, current ?? resolvedHiddenIds))
      closeMenu()
    },
    [closeMenu, resolvedHiddenIds, setHiddenIds],
  )

  const togglePin = useCallback(
    (agent: { id: string; name: string }) => {
      setPins((current) =>
        current.some((pin) => pin.id === agent.id)
          ? unpinAgent(agent.id, current)
          : pinAgent(agent, current),
      )
      closeMenu()
    },
    [closeMenu, setPins],
  )

  const dropPin = useCallback(
    (event: ReactDragEvent) => {
      event.preventDefault()
      const payload = parseAgentDragPayload(event.dataTransfer)
      setDropActive(false)
      finishDrag()
      if (!payload) return
      // Already-pinned drops on empty grid space are a no-op; tile drops reorder.
      setPins((current) =>
        current.some((pin) => pin.id === payload.id) ? current : pinAgent(payload, current),
      )
    },
    [finishDrag, setDropActive, setPins],
  )

  const dropPinReorder = useCallback(
    (event: ReactDragEvent, beforeId: string) => {
      event.preventDefault()
      event.stopPropagation()
      const payload = parseAgentDragPayload(event.dataTransfer)
      finishDrag()
      if (!payload?.id || payload.id === beforeId) return
      setPins((current) => {
        if (current.some((pin) => pin.id === payload.id)) {
          return movePinnedAgent(payload.id, beforeId, current)
        }
        return pinAgent(payload, current)
      })
    },
    [finishDrag, setPins],
  )

  const dropUnfavourite = useCallback(
    (event: ReactDragEvent) => {
      event.preventDefault()
      const payload = parseAgentDragPayload(event.dataTransfer)
      finishDrag()
      if (!payload?.id) return
      setPins((current) =>
        current.some((pin) => pin.id === payload.id) ? unpinAgent(payload.id, current) : current,
      )
    },
    [finishDrag, setPins],
  )

  const allowListUnfavourite = useCallback(
    (event: ReactDragEvent) => {
      const fromId = peekRailDrag() || parseAgentDragPayload(event.dataTransfer)?.id
      if (!isPinnedId(fromId)) return
      event.preventDefault()
      try {
        event.dataTransfer.dropEffect = 'move'
      } catch {
        /* synthetic events may omit dataTransfer */
      }
      setListDropActive(true)
    },
    [isPinnedId, setListDropActive],
  )

  const dropHide = useCallback(
    (event: ReactDragEvent) => {
      event.preventDefault()
      const payload = parseAgentDragPayload(event.dataTransfer)
      finishDrag()
      if (!payload?.id) return
      // Already hidden (or a drop that never left the source row) is a no-op.
      if (resolvedHiddenIds.includes(payload.id)) return
      hideFromRail(payload.id)
    },
    [finishDrag, hideFromRail, resolvedHiddenIds],
  )

  const allowRowDrop = useCallback(
    (event: ReactDragEvent, targetId: string) => {
      const fromId = peekRailDrag() || parseAgentDragPayload(event.dataTransfer)?.id
      if (!fromId || fromId === targetId) {
        try {
          event.dataTransfer.dropEffect = 'none'
        } catch {
          /* synthetic events may omit dataTransfer */
        }
        return
      }
      event.preventDefault()
      try {
        event.dataTransfer.dropEffect = 'move'
      } catch {
        /* synthetic events may omit dataTransfer */
      }
      setDropTargetId(targetId)
    },
    [setDropTargetId],
  )

  const dropReorder = useCallback(
    (event: ReactDragEvent, targetId: string) => {
      event.preventDefault()
      event.stopPropagation()
      const fromId = peekRailDrag() || parseAgentDragPayload(event.dataTransfer)?.id
      if (fromId && fromId !== targetId) {
        const targetSection = sectionIdForAgent(targetId, sectionState)
        setSectionState((current) => moveAgentToSection(current, fromId, targetSection))
        // #761: relative placement — the pointer's half of the target row
        // decides above/below; dropping onto any row of a section also assigns
        // into that section (above). Pinned drops unpin into place either way.
        const half = dropHalfFromClientY(event.clientY, event.currentTarget.getBoundingClientRect())
        if (isPinnedId(fromId)) {
          setPins((current) => unpinAgent(fromId, current))
        }
        if (half === 'below') {
          reorderAfter(fromId, targetId)
        } else {
          reorderBefore(fromId, targetId)
        }
      }
      finishDrag()
    },
    [finishDrag, isPinnedId, reorderAfter, reorderBefore, sectionState, setPins, setSectionState],
  )

  const allowSectionDrop = useCallback(
    (event: ReactDragEvent, sectionId: string) => {
      const fromId = peekRailDrag() || parseAgentDragPayload(event.dataTransfer)?.id
      if (!fromId) {
        try {
          event.dataTransfer.dropEffect = 'none'
        } catch {
          /* synthetic events may omit dataTransfer */
        }
        return
      }
      event.preventDefault()
      try {
        event.dataTransfer.dropEffect = 'move'
      } catch {
        /* synthetic events may omit dataTransfer */
      }
      setSectionDropId(sectionId)
    },
    [setSectionDropId],
  )

  const dropOnSection = useCallback(
    (event: ReactDragEvent, sectionId: string) => {
      event.preventDefault()
      event.stopPropagation()
      const fromId = peekRailDrag() || parseAgentDragPayload(event.dataTransfer)?.id
      if (fromId) {
        if (isPinnedId(fromId)) {
          setPins((current) => unpinAgent(fromId, current))
        }
        setSectionState((current) => moveAgentToSection(current, fromId, sectionId))
      }
      finishDrag()
    },
    [finishDrag, isPinnedId, setPins, setSectionState],
  )

  const dropOnSelf = useCallback(
    (event: ReactDragEvent) => {
      event.preventDefault()
      event.stopPropagation()
      const fromId = peekRailDrag() || parseAgentDragPayload(event.dataTransfer)?.id
      if (isPinnedId(fromId)) {
        setPins((current) => unpinAgent(fromId!, current))
      }
      finishDrag()
    },
    [finishDrag, isPinnedId, setPins],
  )

  const beginRowDrag = useCallback(
    (event: ReactDragEvent, agent: { id: string; name: string }) => {
      try {
        event.dataTransfer.clearData('text/uri-list')
        event.dataTransfer.clearData('URL')
        event.dataTransfer.clearData('text/html')
      } catch {
        /* jsdom DataTransfer may be a stub */
      }
      writeAgentDragPayload(event.dataTransfer, agent)
      beginRailDrag(agent.id)
      try {
        event.dataTransfer.effectAllowed = 'copyMove'
        event.dataTransfer.clearData('text/uri-list')
        event.dataTransfer.clearData('URL')
        event.dataTransfer.clearData('text/html')
      } catch {
        /* jsdom DataTransfer may be a stub */
      }
      setDraggingId(agent.id)
    },
    [setDraggingId],
  )

  return {
    finishDrag,
    hideFromRail,
    hideAgent,
    unhideAgent,
    togglePin,
    dropPin,
    dropPinReorder,
    dropUnfavourite,
    allowListUnfavourite,
    dropHide,
    allowRowDrop,
    dropReorder,
    allowSectionDrop,
    dropOnSection,
    dropOnSelf,
    beginRowDrag,
  }
}
