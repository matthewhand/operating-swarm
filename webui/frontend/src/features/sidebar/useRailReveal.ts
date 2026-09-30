/**
 * #1709 — the rail has to SHOW that a seat was selected.
 *
 * Adding a chat with an existing agent posts a new Django session and writes
 * `?blueprint=<seat>&session=<id>`. The URL already drives the active
 * highlight (`lib/railActive.ts`), but two things stood between that and the
 * operator seeing the switch:
 *
 *  - a collapsed section renders no rows at all, so the highlight was
 *    invisible on exactly the seats a new chat was most likely to land on;
 *  - the rail scroller is long, so an off-screen seat stayed off-screen.
 *
 * So one invariant, applied whenever the active seat changes: its section is
 * expanded and its row is scrolled into view. It runs on *change* only, so a
 * deliberate collapse of the section the operator is already looking at sticks.
 *
 * #1805 — and the SCROLL half of that invariant is one-shot per selection.
 * `visibleRowIds` used to be a dependency of the scroll effect, and it is a
 * fresh array on every catalog rebuild (health tick, remotes refresh, a
 * refocus refetch, a reorder), so the effect re-ran `scrollIntoView` with the
 * selection UNCHANGED: free-scrolling the rail got dragged back to the
 * selected seat. The list is still read, but as content — a seat JOINING it
 * is the one non-selection moment a row that should be on screen appears
 * (#1709's late catalog), and a same-seat rebuild is not a reason to move the
 * operator. Allowlisted triggers stay exactly: Alt+Arrow browse, a created
 * agent, a click-select, and the deep link the rail opens on.
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from 'react'
import { setSectionCollapsed, type RailSectionsState } from '../../lib/railSections'

export interface RailRevealRow {
  id: string
}

export interface RailRevealBlock<T extends RailRevealRow> {
  id: string
  collapsed: boolean
  rows: readonly T[]
}

export interface RailRevealOptions<T extends RailRevealRow> {
  /** The seat the URL says is open (`activeRailId(...)`), or '' off-chat. */
  activeRail: string
  /** The rendered section blocks, so the seat's own section can be found. */
  sectionBlocks: readonly RailRevealBlock<T>[]
  /**
   * Rail row ids. Read as CONTENT by #1805: the reveal follows the active
   * seat JOINING this list (a late catalog) and ignores it churning.
   */
  visibleRowIds: readonly string[]
  /** The rail scroller (`nav.os-rail-scroller`) that holds the rows. */
  navScrollRef: MutableRefObject<HTMLElement | null>
  setSectionState: Dispatch<SetStateAction<RailSectionsState>>
  setOsCollapsed: Dispatch<SetStateAction<boolean>>
  setRemoteCollapsed: Dispatch<SetStateAction<boolean>>
  setCliCollapsed: Dispatch<SetStateAction<boolean>>
  setApiCollapsed: Dispatch<SetStateAction<boolean>>
  setSubagentsCollapsed: Dispatch<SetStateAction<boolean>>
}

/**
 * Attribute-selector safe id. Rail ids are slugs (`codey`, `team:core`), but
 * `CSS.escape` is the correct tool and jsdom's copy is not guaranteed.
 */
function attrValue(railId: string): string {
  const escaped = railId.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
  return typeof CSS !== 'undefined' && typeof CSS.escape === 'function'
    ? CSS.escape(railId)
    : escaped
}

/** The rail row element for a seat id, or null when the row is not mounted. */
export function railRowNode(
  container: HTMLElement | null | undefined,
  railId: string,
): HTMLElement | null {
  if (!container || !railId) return null
  return container.querySelector<HTMLElement>(
    `.os-agent-row[data-agent-id="${attrValue(railId)}"]`,
  )
}

/** The section block holding `railId`, or undefined when the seat is not listed. */
export function railBlockForSeat<T extends RailRevealRow>(
  blocks: readonly RailRevealBlock<T>[],
  railId: string,
): RailRevealBlock<T> | undefined {
  if (!railId) return undefined
  return blocks.find((block) => block.rows.some((row) => row.id === railId))
}

export function useRailReveal<T extends RailRevealRow>(opts: RailRevealOptions<T>) {
  const {
    activeRail,
    sectionBlocks,
    visibleRowIds,
    navScrollRef,
    setSectionState,
    setOsCollapsed,
    setRemoteCollapsed,
    setCliCollapsed,
    setApiCollapsed,
    setSubagentsCollapsed,
  } = opts

  // The kind sections keep their collapsed flag in component state; every
  // other section (custom + Unassigned) keeps it in the persisted bag. The
  // reveal has to reach both, exactly as the section header's toggle does.
  const kindSetters = useMemo(
    () =>
      ({
        os: setOsCollapsed,
        remote: setRemoteCollapsed,
        cli: setCliCollapsed,
        api: setApiCollapsed,
        subagents: setSubagentsCollapsed,
      }) as Record<string, Dispatch<SetStateAction<boolean>>>,
    [
      setApiCollapsed,
      setCliCollapsed,
      setOsCollapsed,
      setRemoteCollapsed,
      setSubagentsCollapsed,
    ],
  )

  const expandSection = useCallback(
    (sectionId: string) => {
      const kindSetter = kindSetters[sectionId]
      if (kindSetter) kindSetter(false)
      else setSectionState((current) => setSectionCollapsed(current, sectionId, false))
    },
    [kindSetters, setSectionState],
  )

  // The seat we have already revealed. Seeded on mount, so a deep link does
  // not count as a "change" and re-expand a section the operator collapsed.
  const revealedRef = useRef(activeRail)
  // Bumped when expanding, so the scroll runs again against the rows that the
  // expand only mounts on the next render.
  const [revealPass, setRevealPass] = useState(0)
  // #1805: the seat whose row has been scrolled into view, '' while the
  // current selection still owes one. This is the allowlist as a latch —
  // selection change, a row joining the list, or the expand's second pass
  // scroll ONCE; free scroll, a health tick and a reorder do not scroll at all.
  const revealedRowRailRef = useRef('')

  useEffect(() => {
    if (!activeRail || revealedRef.current === activeRail) return
    revealedRef.current = activeRail
    const block = railBlockForSeat(sectionBlocks, activeRail)
    if (block?.collapsed) {
      expandSection(block.id)
      setRevealPass((pass) => pass + 1)
    }
  }, [activeRail, expandSection, sectionBlocks])

  /* #1805 — the row's presence, as a VALUE rather than an array identity.
   * '' means "the active seat has no row in the list yet" (the catalog has
   * not landed); the seat id means it does. A rebuild that lists the same
   * seats in a new array leaves this string equal, so the reveal below does
   * not re-run — while a seat that ARRIVES flips it and gets its one scroll. */
  const activeRowListed = useMemo(
    () => (visibleRowIds.includes(activeRail) ? activeRail : ''),
    [visibleRowIds, activeRail],
  )

  useEffect(() => {
    if (!activeRail || !activeRowListed) return
    // Already shown for this selection: a free scroll, a health tick, a
    // section toggle or a list rebuild is not a reason to move the operator.
    if (revealedRowRailRef.current === activeRail) return
    const node = railRowNode(navScrollRef.current, activeRail)
    // jsdom and older browsers have no `scrollIntoView`; the reveal is a
    // convenience, never a hard dependency. The latch stays unset so a later
    // pass (the expand's `revealPass`, the row finally mounting) can try.
    if (typeof node?.scrollIntoView !== 'function') return
    revealedRowRailRef.current = activeRail
    node.scrollIntoView({ block: 'nearest' })
    // `activeRowListed` covers the list settling (catalog arrived, a seat
    // moved sections); `revealPass` covers the pass an expand schedules.
  }, [activeRail, activeRowListed, navScrollRef, revealPass])
}
