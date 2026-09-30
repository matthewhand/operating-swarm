/**
 * #856 slice C — the sidepane's resize/dock state machine, moved verbatim
 * from AgentSidebar.tsx: persisted width, avatar-only + collapsed states,
 * pointer drag (snap + persist), keyboard resize, and live rail-side follow.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  clampRailWidth,
  snapRailWidthToPoints,
  railSnapThresholdForPins,
  railSnapStep,
  loadRailWidth,
  saveRailWidth,
  isAvatarOnlyWidth,
  MAX_RAIL_WIDTH,
  isFullyCollapsedWidth,
  COLLAPSED_RAIL_WIDTH,
  defaultRailWidth,
  railExpandWidthForPins,
  RAIL_WIDTH_STORAGE_KEY,
} from '../../lib/railResize'
import { loadRailSide, RAIL_SIDE_EVENT, type RailSide } from '../../lib/railSide'

export interface UseRailResizeOptions {
  /** Mobile drawer: resize states are desktop-only. */
  narrow: boolean
  /** Drawer conceal (mobile) delegates to the parent's close. */
  onClose?: () => void
  /**
   * #1683: how many tiles the pinned grid is rendering. It selects the
   * *rigid* column detents (`1..min(pins, 4)` of them) and, with it, where the
   * #1262 `RAIL_DETENT_ALWAYS` quantisation stops and free-tracking begins:
   * rigid up to `railWidthForColumns(pins)`, free above it. An empty pool has
   * no column detents at all and free-tracks end to end.
   * Defaults to 1 so a caller that does not know yet keeps the #1262 guard
   * rather than silently dropping it.
   */
  pinnedCount?: number
}

export function useRailResize({
  narrow,
  onClose,
  pinnedCount = 1,
}: UseRailResizeOptions) {
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
  // #1683: the pinned grid is the object the column detents (and the #1262
  // quantisation) were measured from. With nothing pinned it renders `--bare`
  // — no tiles, zero height — so a "2-column" stop is a number the operator
  // cannot see. `railSnapThresholdForPins` resolves the whole rule from the pin
  // count and the dragged width:
  //   pins = 0            → RAIL_SNAP_THRESHOLD everywhere (the whole range
  //                         free-tracks; 0 / 88 / 420 still settle)
  //   pins >= 1, w <= top → RAIL_DETENT_ALWAYS (the #1262 wobble guard: at
  //                         these widths some pin is NOT in the grid's first
  //                         row, so it would jump column on every boundary)
  //   pins >= 1, w >  top → RAIL_SNAP_THRESHOLD (every pin is in row 1 at a
  //                         fixed column, so extra width only appends empty
  //                         tracks — measured, see railSnapPointsForPins)
  // The threshold therefore has to be read per drag FRAME, from the dragged
  // width, not once per render: it flips partway through a single drag.
  const snapThresholdFor = useCallback(
    (width: number) => railSnapThresholdForPins(width, pinnedCount),
    [pinnedCount],
  )

  // #1289 laptop-view reclaim: the rail reserves its own slot in the flex row
  // (App.tsx in-flow shell), so a collapsed pane's 0px lets `<main>` stretch.
  // Report the reserved width as a CSS var on the shell root so any
  // absolutely-positioned chrome can follow the same 0px when collapsed
  // instead of leaving a dead gap.
  // #1697: `--os-rail-inset-start` / `--os-rail-inset-end` split that reserved
  // width onto the edge the rail actually docks to, so a workspace-centred
  // overlay (the composer agent/model selector) can inset itself past the
  // sidepane with pure CSS — no measuring, and it follows resize, collapse and
  // the #816 right-dock flip for free.
  useEffect(() => {
    if (typeof document === 'undefined') return
    const reserved = narrow ? null : isCollapsed ? COLLAPSED_RAIL_WIDTH : railWidth
    const root = document.documentElement
    if (reserved === null) {
      root.style.removeProperty('--os-rail-width')
      root.style.removeProperty('--os-rail-inset-start')
      root.style.removeProperty('--os-rail-inset-end')
      return
    }
    root.style.setProperty('--os-rail-width', `${reserved}px`)
    root.style.setProperty(
      '--os-rail-inset-start',
      `${railSide === 'left' ? reserved : 0}px`,
    )
    root.style.setProperty('--os-rail-inset-end', `${railSide === 'right' ? reserved : 0}px`)
    return () => {
      root.style.removeProperty('--os-rail-width')
      root.style.removeProperty('--os-rail-inset-start')
      root.style.removeProperty('--os-rail-inset-end')
    }
  }, [narrow, isCollapsed, railWidth, railSide])

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
    // #1309: restore the *viewport* default, not the desktop 256px constant.
    // Collapsing then re-expanding on a laptop must return to the compact
    // one-column default (118px), not jump straight to the wide desktop rail.
    //
    // #1712: pin-aware. Expand from ultra-compact now opens to the width that
    // FITS the pinned grid — `min(pins, 3)` columns — instead of the viewport
    // default, which is 256px (a ~2.5-column mid-width that is not a detent at
    // all) on desktop, and one column on a laptop whatever the pin count. Four
    // pins used to open into a one-wide pane and stack four deep. The helper
    // keeps the pre-#1712 default for the zero-pin rail, which earns no column
    // detent (#1683).
    const next = railExpandWidthForPins(
      pinnedCount,
      typeof window !== 'undefined' ? window.innerWidth : undefined,
    )
    setRailWidth(next)
    saveRailWidth(next)
  }, [pinnedCount])

  // #741: the pill button's click is intent-gated — after a drag from the
  // pill, the trailing click gesture is the END of the resize, not a toggle.
  const handlePillToggle = useCallback(() => {
    if (pillDraggedRef.current) {
      pillDraggedRef.current = false
      return
    }
    if (isAvatarOnly || isCollapsed) {
      expandSidebar()
    }
    else {
      concealSidebar()
    }
  }, [isAvatarOnly, isCollapsed, expandSidebar, concealSidebar])

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
        // #1262 follow-up: quantize every drag frame to the nearest detent
        // (RAIL_DETENT_ALWAYS). Free-tracking between detents made the centred
        // pinned grid re-centre on every pointer move, so the tiles visibly
        // drifted sideways while dragging; snapping means the grid only
        // reflows when the column count actually changes.
        //
        // #1683: the quantisation is now scoped by the PIN COUNT. Below the
        // topmost column detent it is still `RAIL_DETENT_ALWAYS` — there,
        // crossing a track boundary makes a pin that is not in row 1 jump
        // column, which read as the tiles wobbling. Above the topmost column
        // detent every pin sits in row 1 at a fixed column (the grid is
        // `justify-content: start`), so the drag free-tracks and still settles
        // on the ceiling (420). With no pins rendered there is no grid at all,
        // so the whole range free-tracks and 0 / 88 / 420 remain the stops.
        const dragged = startWidthRef.current + direction * delta
        const next = snapRailWidthToPoints(
          dragged,
          railSide,
          snapThresholdFor(dragged),
          pinnedCount,
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
        // #806/#1289/#1262: quantize on release too, so persistence agrees
        // with the (detent-quantized) live drag and the grid never parks on a
        // free-floating width. #1683: the release free-tracks on the same lane
        // the drag walked, using the same per-width threshold.
        const dragged = startWidthRef.current + direction * finalDelta
        const finalWidth = snapRailWidthToPoints(
          dragged,
          railSide,
          snapThresholdFor(dragged),
          pinnedCount,
        )
        setRailWidth(finalWidth)
        saveRailWidth(finalWidth)
      }

      window.addEventListener('pointermove', handlePointerMove)
      window.addEventListener('pointerup', handlePointerUp)
      window.addEventListener('pointercancel', handlePointerUp)
    },
    [railWidth, railSide, snapThresholdFor, pinnedCount],
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
      // #1289: arrows step detent-to-detent (whole pinned-grid columns,
      // avatar-only, collapsed) instead of nudging 12px at a time. #1683: the
      // lane is the pin-dependent one — the SAME set the drag sticks to — so
      // a 2-pin rail steps 88 → 118 → 210 → 420 and never has to stop on a
      // 3-column width it cannot see, and an unpinned rail steps 88 → 420.
      // The ceiling closes the lane, so ArrowRight from the topmost column
      // detent lands on 420 rather than dead-ending short of it.
      const growDelta = railSide === 'right' ? -1 : 1
      if (event.key === 'ArrowLeft') {
        event.preventDefault()
        setRailWidth((prev) => {
          const next = railSnapStep(prev, -growDelta, railSide, pinnedCount)
          saveRailWidth(next)
          return next
        })
      }
      else if (event.key === 'ArrowRight') {
        event.preventDefault()
        setRailWidth((prev) => {
          const next = railSnapStep(prev, growDelta, railSide, pinnedCount)
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
    [railSide, pinnedCount],
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
