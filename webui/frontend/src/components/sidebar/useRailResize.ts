/**
 * #856 slice C — the sidepane's resize/dock state machine, moved verbatim
 * from AgentSidebar.tsx: persisted width, avatar-only + collapsed states,
 * pointer drag (snap + persist), keyboard resize, and live rail-side follow.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  clampRailWidth,
  snapRailWidth,
  loadRailWidth,
  saveRailWidth,
  isAvatarOnlyWidth,
  MAX_RAIL_WIDTH,
  DEFAULT_RAIL_WIDTH,
  isFullyCollapsedWidth,
  COLLAPSED_RAIL_WIDTH,
  defaultRailWidth,
  RAIL_WIDTH_STORAGE_KEY,
} from '../../lib/railResize'
import { loadRailSide, RAIL_SIDE_EVENT, type RailSide } from '../../lib/railSide'

export interface UseRailResizeOptions {
  /** Mobile drawer: resize states are desktop-only. */
  narrow: boolean
  /** Drawer conceal (mobile) delegates to the parent's close. */
  onClose?: () => void
}

export function useRailResize({ narrow, onClose }: UseRailResizeOptions) {
  // #816: which edge the rail docks to ('left' historical default).
  const [railSide, setRailSideState] = useState<RailSide>(() => loadRailSide())
  useEffect(() => {
    // The setting can flip from the settings sheet — follow it live.
    const sync = () => setRailSideState(loadRailSide())
    window.addEventListener(RAIL_SIDE_EVENT, sync)
    return () => window.removeEventListener(RAIL_SIDE_EVENT, sync)
  }, [])

  const [railWidth, setRailWidth] = useState(() =>
    loadRailWidth(typeof window !== 'undefined' ? window.innerWidth : undefined),
  )

  useEffect(() => {
    // #1083: if the user has not explicitly customized rail width, adapt default width across laptop/desktop viewports.
    const handleResize = () => {
      try {
        if (!localStorage.getItem(RAIL_WIDTH_STORAGE_KEY)) {
          setRailWidth(defaultRailWidth(window.innerWidth))
        }
      } catch {}
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const [isResizing, setIsResizing] = useState(false)
  const isAvatarOnly = !narrow && isAvatarOnlyWidth(railWidth)
  // #765: the divider-only state — the pane body collapses entirely and only
  // the border spine + the expand pill remain (a strict subset of avatar-only).
  const isCollapsed = !narrow && isFullyCollapsedWidth(railWidth)

  const concealSidebar = useCallback(() => {
    if (narrow) {
      onClose?.()
      return
    }
    // #765: conceal now means the full edge collapse — 0px, divider only.
    setRailWidth(COLLAPSED_RAIL_WIDTH)
    saveRailWidth(COLLAPSED_RAIL_WIDTH)
  }, [narrow, onClose])

  const expandSidebar = useCallback(() => {
    setRailWidth(DEFAULT_RAIL_WIDTH)
    saveRailWidth(DEFAULT_RAIL_WIDTH)
  }, [])

  // #741: the pill button's click is intent-gated — after a drag from the
  // pill, the trailing click gesture is the END of the resize, not a toggle.
  const handlePillToggle = useCallback(() => {
    if (pillDraggedRef.current) {
      pillDraggedRef.current = false
      return
    }
    if (isAvatarOnly) {
      expandSidebar()
    }
    else {
      concealSidebar()
    }
  }, [isAvatarOnly, expandSidebar, concealSidebar])

  const startDragXRef = useRef(0)
  const startWidthRef = useRef(railWidth)
  // #741: set when a drag started on the pill — the follow-up click must be
  // swallowed so the toggle does not fire at drag end.
  const pillDraggedRef = useRef(false)

  // #741: shared drag body — the resizer strip and the pill (via intent
  // detection) both funnel here, so a grab anywhere on the divider resizes.
  const beginResizeDrag = useCallback(
    (startClientX: number, pointerId: number, target: HTMLElement | null) => {
      setIsResizing(true)
      startDragXRef.current = startClientX
      startWidthRef.current = railWidth
      try {
        target?.setPointerCapture(pointerId)
      }
      catch {}

      // #816: on the right edge the row grows leftwards, so the pointer
      // vector mirrors (negative delta = wider).
      const direction = railSide === 'right' ? -1 : 1

      const handlePointerMove = (e: PointerEvent) => {
        const delta = e.clientX - startDragXRef.current
        // #806: snapping clamp — the avatar-only dead zone is gone.
        const next = snapRailWidth(
          startWidthRef.current + direction * delta,
          window.innerWidth,
        )
        setRailWidth(next)
      }

      const handlePointerUp = (e: PointerEvent) => {
        setIsResizing(false)
        try {
          target?.releasePointerCapture(e.pointerId)
        }
        catch {}
        window.removeEventListener('pointermove', handlePointerMove)
        window.removeEventListener('pointerup', handlePointerUp)
        window.removeEventListener('pointercancel', handlePointerUp)
        const finalDelta = e.clientX - startDragXRef.current
        // #806: snap on release too, so persistence agrees with the drag.
        const finalWidth = snapRailWidth(
          startWidthRef.current + direction * finalDelta,
          window.innerWidth,
        )
        setRailWidth(finalWidth)
        saveRailWidth(finalWidth)
      }

      window.addEventListener('pointermove', handlePointerMove)
      window.addEventListener('pointerup', handlePointerUp)
      window.addEventListener('pointercancel', handlePointerUp)
    },
    [railWidth, railSide],
  )

  const handleResizeStart = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      event.preventDefault()
      beginResizeDrag(event.clientX, event.pointerId, event.currentTarget)
    },
    [beginResizeDrag],
  )

  const handleResizeKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      // #816: arrows mirror on the right rail — the grow arrow always points
      // toward the content side.
      const growDelta = railSide === 'right' ? -12 : 12
      if (event.key === 'ArrowLeft') {
        event.preventDefault()
        setRailWidth((prev) => {
          const next = clampRailWidth(prev - growDelta, window.innerWidth)
          saveRailWidth(next)
          return next
        })
      }
      else if (event.key === 'ArrowRight') {
        event.preventDefault()
        setRailWidth((prev) => {
          const next = clampRailWidth(prev + growDelta, window.innerWidth)
          saveRailWidth(next)
          return next
        })
      }
      else if (event.key === 'Home') {
        event.preventDefault()
        // #765: Home walks all the way to the collapsed divider-only state.
        setRailWidth(COLLAPSED_RAIL_WIDTH)
        saveRailWidth(COLLAPSED_RAIL_WIDTH)
      }
      else if (event.key === 'End') {
        event.preventDefault()
        const max = clampRailWidth(MAX_RAIL_WIDTH, window.innerWidth)
        setRailWidth(max)
        saveRailWidth(max)
      }
    },
    [railSide],
  )

  return {
    railSide,
    railWidth,
    isResizing,
    /** #741: pill intent flag — the render's onPointerDown resets it. */
    pillDraggedRef,
    isAvatarOnly,
    isCollapsed,
    concealSidebar,
    expandSidebar,
    handlePillToggle,
    beginResizeDrag,
    handleResizeStart,
    handleResizeKeyDown,
    setRailWidth,
  }
}
