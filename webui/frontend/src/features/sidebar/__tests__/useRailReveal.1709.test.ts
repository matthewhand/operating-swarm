/**
 * #1709 — the reveal hook itself.
 *
 * `RailAddChatSelect1709.test.tsx` drives the reported flow through the whole
 * rail, which reaches the custom + Unassigned sections. The kind sections
 * (OS / Remote / CLI / API / Subagents) keep their collapsed flag in component
 * state instead of the persisted bag, so they can only be collapsed
 * interactively — unreachable from an integration mount that starts expanded.
 * That branch is covered here, next to the two lookup helpers.
 *
 * #1805 adds the other half of the contract: the scroll happens ONCE per
 * selection, and a list rebuild (health tick, refocus refetch, reorder) never
 * re-snaps an operator who is free-scrolling.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { railBlockForSeat, railRowNode, useRailReveal } from '../useRailReveal'
import {
  UNASSIGNED_SECTION_ID,
  type RailSectionsState,
} from '../../../lib/railSections'

/** Mirrors what `loadRailSections()` hands the rail: the listed sections exist. */
function seedSections(): RailSectionsState {
  return {
    sections: [{ id: 'sec_work', name: 'Work', collapsed: true }],
    membership: { codey: 'sec_work', stewie: 'sec_work' },
    unassignedCollapsed: true,
  }
}

interface Harness {
  sectionBlocks: Array<{ id: string; collapsed: boolean; rows: Array<{ id: string }> }>
  visibleRowIds: string[]
  activeRail: string
}

function harness(initial: Partial<Harness> = {}) {
  const state: Harness = {
    sectionBlocks: initial.sectionBlocks ?? [],
    // The rail hands over the ids of the rows it RENDERS, so the list and the
    // DOM agree. A row mounted but unlisted is not a state the component can
    // be in, and the reveal reads the list as content (#1805) — so the
    // default mirrors the scroller `beforeEach` builds.
    visibleRowIds: initial.visibleRowIds ?? ['codey', 'stewie'],
    activeRail: initial.activeRail ?? '',
  }
  const calls: string[] = []
  const sectionStates: RailSectionsState[] = []
  const navScrollRef: { current: HTMLElement | null } = { current: null }
  const scrollIntoView = vi.fn()

  const view = renderHook(
    (props: Harness) =>
      useRailReveal<{ id: string }>({
        activeRail: props.activeRail,
        sectionBlocks: props.sectionBlocks,
        visibleRowIds: props.visibleRowIds,
        navScrollRef,
        setSectionState: (update) => {
          const next =
            typeof update === 'function'
              ? (update as (s: RailSectionsState) => RailSectionsState)(
                  sectionStates[sectionStates.length - 1] ?? seedSections(),
                )
              : update
          sectionStates.push(next)
        },
        setOsCollapsed: (v) => calls.push(`os:${v as boolean}`),
        setRemoteCollapsed: (v) => calls.push(`remote:${v as boolean}`),
        setCliCollapsed: (v) => calls.push(`cli:${v as boolean}`),
        setApiCollapsed: (v) => calls.push(`api:${v as boolean}`),
        setSubagentsCollapsed: (v) => calls.push(`subagents:${v as boolean}`),
      }),
    { initialProps: state },
  )

  return {
    view,
    calls,
    sectionStates,
    navScrollRef,
    scrollIntoView,
    async set(next: Partial<Harness>) {
      Object.assign(state, next)
      await act(async () => {
        view.rerender(state)
      })
    },
  }
}

describe('#1709 useRailReveal', () => {
  let scroller: HTMLElement

  beforeEach(() => {
    scroller = document.createElement('nav')
    for (const id of ['codey', 'stewie']) {
      const row = document.createElement('button')
      row.className = 'os-agent-row'
      row.setAttribute('data-agent-id', id)
      row.scrollIntoView = vi.fn()
      scroller.appendChild(row)
    }
    document.body.appendChild(scroller)
  })

  it('expands the kind section holding the newly active seat', async () => {
    const h = harness({
      activeRail: 'codey',
      sectionBlocks: [
        { id: 'cli', collapsed: true, rows: [{ id: 'stewie' }] },
        { id: 'api', collapsed: false, rows: [{ id: 'codey' }] },
      ],
    })
    h.navScrollRef.current = scroller

    await h.set({ activeRail: 'stewie' })

    // Only the section that actually holds the seat moves, and only to open.
    expect(h.calls).toEqual(['cli:false'])
  })

  it('expands a custom section through the persisted section bag', async () => {
    const h = harness({
      activeRail: 'codey',
      sectionBlocks: [
        { id: 'sec_work', collapsed: true, rows: [{ id: 'codey' }, { id: 'stewie' }] },
      ],
    })
    h.navScrollRef.current = scroller

    await h.set({ activeRail: 'stewie' })

    expect(h.calls).toEqual([])
    expect(h.sectionStates.at(-1)).toMatchObject({
      sections: [{ id: 'sec_work', collapsed: false }],
      unassignedCollapsed: true,
    })
  })

  it('expands Unassigned through the persisted bag, not a kind setter', async () => {
    const h = harness({
      activeRail: 'codey',
      sectionBlocks: [
        { id: UNASSIGNED_SECTION_ID, collapsed: true, rows: [{ id: 'stewie' }] },
      ],
    })
    h.navScrollRef.current = scroller

    await h.set({ activeRail: 'stewie' })

    expect(h.calls).toEqual([])
    expect(h.sectionStates.at(-1)?.unassignedCollapsed).toBe(false)
  })

  it('leaves an already-expanded section alone', async () => {
    const h = harness({
      activeRail: 'codey',
      sectionBlocks: [
        { id: 'sec_work', collapsed: false, rows: [{ id: 'codey' }] },
      ],
    })
    h.navScrollRef.current = scroller

    await h.set({ activeRail: 'stewie' })

    expect(h.calls).toEqual([])
    expect(h.sectionStates).toEqual([])
  })

  it('does not reveal the seat the rail opened on (a deep link is not a change)', async () => {
    const h = harness({
      activeRail: 'stewie',
      sectionBlocks: [
        { id: 'cli', collapsed: true, rows: [{ id: 'stewie' }] },
      ],
    })
    h.navScrollRef.current = scroller

    await act(async () => {
      await Promise.resolve()
    })

    expect(h.calls).toEqual([])
  })

  it('scrolls only the active row into view', async () => {
    const h = harness({ activeRail: 'codey' })
    h.navScrollRef.current = scroller

    await h.set({ activeRail: 'stewie' })

    const codey = railRowNode(scroller, 'codey') as HTMLElement
    const stewie = railRowNode(scroller, 'stewie') as HTMLElement
    expect(codey.scrollIntoView).not.toHaveBeenCalled()
    expect(stewie.scrollIntoView).toHaveBeenCalledTimes(1)
    expect(stewie.scrollIntoView).toHaveBeenCalledWith({ block: 'nearest' })
  })

  it('survives a row that is not mounted and a scroller with no scrollIntoView', async () => {
    const h = harness({ activeRail: '' })
    h.navScrollRef.current = scroller

    await h.set({ activeRail: 'not-a-real-seat' })
    expect(h.calls).toEqual([])

    // A browser without the API is a no-op, not a throw.
    const stale = railRowNode(scroller, 'codey') as HTMLElement
    stale.scrollIntoView = undefined as unknown as () => void
    await h.set({ activeRail: 'codey' })
    expect(h.calls).toEqual([])
  })
})

/**
 * #1805 — the reported bug: free-scrolling the sidepane got yanked back to
 * the selected seat. `visibleRowIds` was a dependency of the scroll effect and
 * it is a fresh array on every catalog rebuild, so a health tick or a refocus
 * refetch re-ran `scrollIntoView` with the selection unchanged.
 */
describe('#1805 free scroll never re-snaps the selection', () => {
  let scroller: HTMLElement

  beforeEach(() => {
    scroller = document.createElement('nav')
    for (const id of ['codey', 'stewie', 'ada']) {
      const row = document.createElement('button')
      row.className = 'os-agent-row'
      row.setAttribute('data-agent-id', id)
      row.scrollIntoView = vi.fn()
      scroller.appendChild(row)
    }
    document.body.appendChild(scroller)
  })

  it('ignores a row list that rebuilds with the same seats', async () => {
    const h = harness({ activeRail: '', visibleRowIds: ['codey', 'stewie', 'ada'] })
    h.navScrollRef.current = scroller

    // A click-select (or Alt+Arrow) moved the selection: one reveal.
    await h.set({ activeRail: 'stewie' })
    const stewie = railRowNode(scroller, 'stewie') as HTMLElement
    expect(stewie.scrollIntoView).toHaveBeenCalledTimes(1)

    // Free scroll, then the list churns underneath it: a new array carrying
    // the same seats (health tick / remotes refresh / refocus refetch).
    await h.set({ visibleRowIds: ['codey', 'stewie', 'ada'] })
    await h.set({ visibleRowIds: ['stewie', 'ada', 'codey'] })
    await h.set({ sectionBlocks: [{ id: 'cli', collapsed: true, rows: [{ id: 'stewie' }] }] })

    expect(stewie.scrollIntoView).toHaveBeenCalledTimes(1)
    // And no other row was dragged into view either.
    expect((railRowNode(scroller, 'codey') as HTMLElement).scrollIntoView).not.toHaveBeenCalled()
    expect((railRowNode(scroller, 'ada') as HTMLElement).scrollIntoView).not.toHaveBeenCalled()
  })

  it('scrolls a created agent into view exactly once', async () => {
    const h = harness({ activeRail: '', visibleRowIds: ['codey', 'stewie'] })
    h.navScrollRef.current = scroller

    // Add-agent: the new seat joins the list and the URL moves to it, which is
    // the one create path the rail has (the wizard navigates too).
    await h.set({ visibleRowIds: ['ada', 'codey', 'stewie'], activeRail: 'ada' })
    const ada = railRowNode(scroller, 'ada') as HTMLElement
    expect(ada.scrollIntoView).toHaveBeenCalledTimes(1)

    // The catalog settles again a tick later — the reveal must not repeat.
    await h.set({ visibleRowIds: ['ada', 'codey', 'stewie', 'nova'] })
    expect(ada.scrollIntoView).toHaveBeenCalledTimes(1)
  })

  it('reveals once per browse step, in both directions', async () => {
    const h = harness({ activeRail: '', visibleRowIds: ['codey', 'stewie', 'ada'] })
    h.navScrollRef.current = scroller

    // Alt+Down three times, then back up once: a step that lands on a seat the
    // rail already revealed once still reveals once more, because the operator
    // asked for it.
    for (const id of ['codey', 'stewie', 'ada', 'stewie']) {
      await h.set({ activeRail: id })
    }

    for (const id of ['codey', 'ada']) {
      expect((railRowNode(scroller, id) as HTMLElement).scrollIntoView).toHaveBeenCalledTimes(1)
    }
    expect((railRowNode(scroller, 'stewie') as HTMLElement).scrollIntoView).toHaveBeenCalledTimes(2)
  })

  it('reveals a seat whose row only appears once the catalog lands', async () => {
    // Selected before the rail has listed it (deep link into a seat the first
    // fetch has not returned yet).
    const h = harness({ activeRail: 'stewie', visibleRowIds: ['codey'] })
    h.navScrollRef.current = scroller

    await h.set({ visibleRowIds: ['codey', 'stewie'] })

    expect((railRowNode(scroller, 'stewie') as HTMLElement).scrollIntoView).toHaveBeenCalledTimes(1)
  })

  it('reveals after the expand mounts the row, still only once', async () => {
    // #1709's collapsed-section path: the seat is listed but its row is not
    // rendered, so the first pass finds nothing and the expand's second pass
    // does the scroll. The latch must not be spent by the empty first pass.
    // Mounted here rather than through `harness` because the row has to appear
    // AS the expand runs — the same batch the reveal's second pass reads.
    const nav = document.createElement('nav')
    document.body.appendChild(nav)
    const navScrollRef = { current: nav as HTMLElement | null }
    const collapsedCli = [
      { id: 'cli', collapsed: true, rows: [{ id: 'stewie' }] },
      { id: 'api', collapsed: false, rows: [{ id: 'codey' }] },
    ]
    const openCli = [
      { id: 'cli', collapsed: false, rows: [{ id: 'stewie' }] },
      { id: 'api', collapsed: false, rows: [{ id: 'codey' }] },
    ]
    const view = renderHook(
      (props: { activeRail: string; sectionBlocks: typeof collapsedCli }) =>
        useRailReveal<{ id: string }>({
          activeRail: props.activeRail,
          sectionBlocks: props.sectionBlocks,
          visibleRowIds: ['codey', 'stewie'],
          navScrollRef,
          setSectionState: () => undefined,
          setOsCollapsed: () => undefined,
          setRemoteCollapsed: () => undefined,
          setCliCollapsed: () => {
            // The expand renders the section's rows on the next render.
            const row = document.createElement('button')
            row.className = 'os-agent-row'
            row.setAttribute('data-agent-id', 'stewie')
            row.scrollIntoView = vi.fn()
            nav.appendChild(row)
          },
          setApiCollapsed: () => undefined,
          setSubagentsCollapsed: () => undefined,
        }),
      { initialProps: { activeRail: 'codey', sectionBlocks: collapsedCli } },
    )

    await view.rerender({ activeRail: 'stewie', sectionBlocks: collapsedCli })

    const stewie = railRowNode(nav, 'stewie') as HTMLElement
    expect(stewie.scrollIntoView).toHaveBeenCalledTimes(1)

    // The list settles again after the expand — still the one reveal.
    await view.rerender({ activeRail: 'stewie', sectionBlocks: openCli })
    expect(stewie.scrollIntoView).toHaveBeenCalledTimes(1)
  })
})

describe('#1709 railBlockForSeat', () => {
  const blocks = [
    { id: 'os', collapsed: false, rows: [{ id: 'a' }] },
    { id: 'cli', collapsed: true, rows: [{ id: 'b' }, { id: 'c' }] },
  ]

  it('finds the block owning the seat', () => {
    expect(railBlockForSeat(blocks, 'c')?.id).toBe('cli')
  })

  it('returns undefined for an unlisted or blank seat', () => {
    expect(railBlockForSeat(blocks, 'zzz')).toBeUndefined()
    expect(railBlockForSeat(blocks, '')).toBeUndefined()
  })
})
