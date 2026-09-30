/**
 * #856 slice C — AgentSidebar decomposition begins.
 *
 * 1. The rail model (row types + pure kind mappers) lives in
 *    `sidebar/railModel.ts` and AgentSidebar imports it from there —
 *    no duplicate definitions remain in the monolith.
 * 2. The resize/dock state machine lives in `sidebar/useRailResize.ts`:
 *    load-from-storage on mount, conceal/expand persist, pointer drags snap
 *    and persist on release, keyboard resize clamps and persists, and the
 *    whole surface mirrors for a right-docked rail.
 */
import { describe, expect, it } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  DEFAULT_RAIL_WIDTH,
  COLLAPSED_RAIL_WIDTH,
  MAX_RAIL_WIDTH,
  RAIL_SNAP_POINTS,
  railSnapPointsForPins,
  ONE_COL_RAIL_WIDTH,
  TWO_COL_RAIL_WIDTH,
  THREE_COL_RAIL_WIDTH,
  ULTRACOMPACT_RAIL_WIDTH,
  loadRailWidth,
  saveRailWidth,
} from '../../lib/railResize'
import { useRailResize } from '../sidebar/useRailResize'
import {
  isHerdrAgent,
  isCliRailAgent,
  isApiRailAgent,
  isBlueprintRailAgent,
  isRemoteRailAgent,
  toSidebarCli,
  toSidebarCliName,
  toSidebarHerdr,
  toSidebarDynamic,
  sidebarHref,
} from '../../features/sidebar/rows'

describe('#856 slice C: rail model module', () => {
  it('classifies herdr seats by kind or id prefix', () => {
    expect(isHerdrAgent({ id: 'herdr:alpha', kind: undefined })).toBe(true)
    expect(isHerdrAgent({ id: 'x', kind: 'herdr' })).toBe(true)
    expect(isHerdrAgent({ id: 'x', kind: 'api' })).toBe(false)
  })

  it('maps CLI rail rows with the not-on-PATH annotation', () => {
    const row = toSidebarCli({
      id: 'agy',
      name: 'agy',
      description: 'Agy CLI',
      kind: 'cli',
      cli: 'agy',
      installed: false,
    } as never)
    expect(row.kind).toBe('cli')
    expect(row.description).toContain('(not on PATH)')
    expect(row.cli).toBe('agy')
  })

  it('maps herdr rows onto the namespaced herdr: id', () => {
    const row = toSidebarHerdr({ name: 'alpha', remote: 'rc' } as never)
    expect(row.id).toBe('herdr:alpha')
    expect(row.description).toContain('Herdr · rc')
  })

  it('maps dynamic subagents with their spawn timestamp (#843)', () => {
    const row = toSidebarDynamic({
      id: 'sub1',
      name: 'Scout',
      role: 'scout',
      timestamp: 1234,
      avatar_path: 'a.png',
    } as never)
    expect(row.kind).toBe('subagent')
    expect(row.last_message_at).toBe(1234)
    expect(row.avatar_path).toBe('a.png')
  })

  it('routes herdr seats through the herdr chat href', () => {
    const href = sidebarHref({ id: 'herdr:alpha', kind: 'herdr' })
    expect(href).toContain('remote=herdr')
    expect(sidebarHref({ id: 'api_agent', kind: 'api' })).not.toContain('remote=')
  })

  it('carries a CLI seat declared cli on the chat href', () => {
    // A designer-created CLI seat navigates with its declared cli so ChatPage
    // resolves that exact CLI (and its models), not an inferred fallback.
    const designed = sidebarHref({ id: 'hass-eng', kind: 'design', cli: 'opencode' })
    expect(designed).toContain('blueprint=hass-eng')
    expect(designed).toContain('cli=opencode')
    // `antigravity` is the rail id; `agy` is the catalog binary it runs.
    expect(sidebarHref({ id: 'antigravity', kind: 'design', cli: 'agy' })).toContain(
      'cli=agy',
    )
    // No declared cli → no empty param.
    expect(sidebarHref({ id: 'api_agent', kind: 'api' })).not.toContain('cli=')
  })

  // A derived CLI rail row (one per discovered/configured CLI) has a
  // `<name>_agent` id that classifies as an API seat client-side, so it must
  // route through the explicit blueprint+cli query instead.
  it('maps a CLI name to a derived rail row', () => {
    const row = toSidebarCliName('agy')
    expect(row.id).toBe('agy_agent')
    expect(row.name).toBe('agy')
    expect(row.kind).toBe('cli')
    expect(row.cli).toBe('agy')
    expect(row.rail).toBe(true)
    expect(row.installed).toBe(true)
    expect(row.compiled).toBe(true)
    expect(row.abbreviation).toBeNull()
    expect(row.required_mcp_servers).toEqual([])
    expect(row.description).toContain('agy')
  })

  it('routes a derived CLI row to blueprint=cli_agent&cli=<name>', () => {
    expect(sidebarHref(toSidebarCliName('agy'))).toBe('/chat?blueprint=cli_agent&cli=agy')
    expect(sidebarHref(toSidebarCliName('opencode'))).toBe(
      '/chat?blueprint=cli_agent&cli=opencode',
    )
  })

  it('carries the default cli on the generic cli_agent row href', () => {
    // Its `cli` is only the default pick — the generic seat must not turn into
    // a per-CLI URL.
    expect(sidebarHref({ id: 'cli_agent', kind: 'cli', cli: 'grok' })).toBe(
      '/chat?blueprint=cli_agent&cli=grok',
    )
  })

  it('routes a no-cli row (and api_agent) through agentChatHref', () => {
    expect(sidebarHref({ id: 'api_agent', kind: 'api', cli: '' })).toBe(
      '/chat?blueprint=api_agent',
    )
    expect(sidebarHref({ id: 'codey', kind: 'blueprint' })).toBe('/chat?blueprint=codey')
  })

  it('kind predicates agree with the mappers', () => {
    expect(isCliRailAgent({ kind: 'cli' })).toBe(true)
    expect(isApiRailAgent({ kind: 'api' })).toBe(true)
    expect(isApiRailAgent({ id: 'api_agent' })).toBe(true)
    expect(isBlueprintRailAgent({ kind: 'blueprint' })).toBe(true)
  })

  it('recognises remote rail agents by kind, impl id, and herdr prefix', () => {
    expect(isRemoteRailAgent({ id: 'herdr:w3:p1', kind: 'herdr' })).toBe(true)
    expect(isRemoteRailAgent({ id: 'remote:omb', kind: 'remote' })).toBe(true)
    // ADR-011 remote implementations are not a user-facing kind: probe ids too.
    expect(isRemoteRailAgent({ id: 'hermes', kind: null })).toBe(true)
    expect(isRemoteRailAgent({ id: 'omb', kind: null })).toBe(true)
    // Kind wins: a CLI seat (even bound to a remote endpoint) stays CLI.
    expect(isRemoteRailAgent({ id: 'agy_agent', kind: 'cli', remote: 'omb' })).toBe(false)
    expect(isRemoteRailAgent({ id: 'api_agent', kind: 'api' })).toBe(false)
    expect(isRemoteRailAgent({ id: 'codey', kind: 'blueprint' })).toBe(false)
  })

  it('AgentSidebar no longer defines the model inline', () => {
    const src = readFileSync(join(__dirname, '..', 'AgentSidebar.tsx'), 'utf-8')
    expect(src).not.toContain('function toSidebarHerdr(')
    expect(src).not.toContain('function toSidebarCli(')
  })
})

describe('#856 slice C: useRailResize', () => {
  it('loads the persisted width on mount', () => {
    saveRailWidth(400)
    const { result } = renderHook(() => useRailResize({ narrow: false }))
    expect(result.current.railWidth).toBe(400)
  })

  it('conceal collapses to the divider-only width and persists', () => {
    saveRailWidth(600)
    const { result } = renderHook(() => useRailResize({ narrow: false }))
    act(() => result.current.concealSidebar())
    expect(result.current.railWidth).toBe(COLLAPSED_RAIL_WIDTH)
    expect(result.current.isCollapsed).toBe(true)
    expect(loadRailWidth()).toBe(COLLAPSED_RAIL_WIDTH)
  })

  it('expand restores the viewport default width and persists (#1309)', () => {
    // #1098: innerWidth is a getter-only accessor here; bare assignment throws
    // 'read only'. Always go through defineProperty (configurable so the reset
    // in the finally block keeps working).
    const prevWidth = window.innerWidth
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1280 })
    try {
      saveRailWidth(COLLAPSED_RAIL_WIDTH)
      const { result } = renderHook(() => useRailResize({ narrow: false }))
      act(() => result.current.expandSidebar())
      // A laptop viewport expands back to the compact one-column rail, not the
      // desktop 256px constant.
      expect(result.current.railWidth).toBe(ONE_COL_RAIL_WIDTH)
      expect(loadRailWidth()).toBe(ONE_COL_RAIL_WIDTH)
    } finally {
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: prevWidth })
    }
  })

  /**
   * #1712 SUPERSEDES the desktop-256 half of this test on a rail with pins.
   *
   * #1309's rule was "expand restores the VIEWPORT default" (256 on desktop,
   * 1 column on a laptop). 256 is not a detent — it is a ~2.5-column mid-width
   * no drag or arrow key can return to — and it ignored the pin count, so four
   * pins opened into a one-wide pane. #1712 replaces it with `min(pins, 3)`
   * columns.
   *
   * The ZERO-pin rail is where #1309 still holds verbatim: with nothing pinned
   * there is no column detent to earn (#1683's empty pool), so expand keeps the
   * viewport default. That is the case pinned below, and the one the two rules
   * agree on. The pinned cases live in `RailExpandSnap1712.test.tsx`.
   */
  it('expand restores the desktop default on wide viewports when nothing is pinned (#1309)', () => {
    const prevWidth = window.innerWidth
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1920 })
    try {
      saveRailWidth(COLLAPSED_RAIL_WIDTH)
      // pinnedCount 0: no tiles, so no column detent.
      const { result } = renderHook(() => useRailResize({ narrow: false, pinnedCount: 0 }))
      act(() => result.current.expandSidebar())
      expect(result.current.railWidth).toBe(DEFAULT_RAIL_WIDTH)
      expect(loadRailWidth()).toBe(DEFAULT_RAIL_WIDTH)
    } finally {
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: prevWidth })
    }
  })

  it('narrow rails never report avatar-only or collapsed', () => {
    const { result } = renderHook(() => useRailResize({ narrow: true }))
    expect(result.current.isAvatarOnly).toBe(false)
    expect(result.current.isCollapsed).toBe(false)
  })

  it('keyboard resize persists clamped widths', () => {
    saveRailWidth(500)
    const { result } = renderHook(() => useRailResize({ narrow: false }))
    const fire = (key: string) =>
      act(() => {
        result.current.handleResizeKeyDown({
          key,
          preventDefault: () => {},
        } as unknown as React.KeyboardEvent<HTMLDivElement>)
      })
    fire('ArrowLeft')
    const afterShrink = loadRailWidth()
    expect(afterShrink).toBeLessThan(500)
    fire('End')
    expect(result.current.railWidth).toBe(MAX_RAIL_WIDTH)
    expect(result.current.railWidth).toBeGreaterThan(afterShrink)
    fire('Home')
    expect(result.current.railWidth).toBe(COLLAPSED_RAIL_WIDTH)
  })

  it('exposes the dock side and follows the rail-side event', () => {
    const { result } = renderHook(() => useRailResize({ narrow: false }))
    expect(result.current.railSide).toBe('left')
  })
})

describe('#1289 useRailResize — pinned-grid snap points', () => {
  it('keyboard ArrowRight steps one snap point at a time', () => {
    // #1683: which lane the arrows walk is a function of the pin count, so this
    // pins 3 — the count that earns the 1/2/3 column detents this asserts.
    saveRailWidth(ONE_COL_RAIL_WIDTH)
    const { result } = renderHook(() => useRailResize({ narrow: false, pinnedCount: 3 }))
    const fire = (key: string) =>
      act(() => {
        result.current.handleResizeKeyDown({
          key,
          preventDefault: () => {},
        } as unknown as React.KeyboardEvent<HTMLDivElement>)
      })

    // The lane is ordered by pixel value: 118 → 210 → 302 → 420 (#1651).
    fire('ArrowRight')
    expect(result.current.railWidth).toBe(TWO_COL_RAIL_WIDTH)
    fire('ArrowRight')
    expect(result.current.railWidth).toBe(THREE_COL_RAIL_WIDTH)
    fire('ArrowRight')
    expect(result.current.railWidth).toBe(MAX_RAIL_WIDTH)
    // floor at the widest detent
    fire('ArrowRight')
    expect(result.current.railWidth).toBe(MAX_RAIL_WIDTH)
  })

  it('keyboard ArrowLeft steps down through avatar-only to collapsed', () => {
    saveRailWidth(ONE_COL_RAIL_WIDTH)
    const { result } = renderHook(() => useRailResize({ narrow: false, pinnedCount: 3 }))
    const fire = (key: string) =>
      act(() => {
        result.current.handleResizeKeyDown({
          key,
          preventDefault: () => {},
        } as unknown as React.KeyboardEvent<HTMLDivElement>)
      })

    fire('ArrowLeft')
    expect(result.current.railWidth).toBe(ULTRACOMPACT_RAIL_WIDTH)
    expect(result.current.isAvatarOnly).toBe(true)
    fire('ArrowLeft')
    expect(result.current.railWidth).toBe(COLLAPSED_RAIL_WIDTH)
    expect(result.current.isCollapsed).toBe(true)
    // floor at the collapsed detent
    fire('ArrowLeft')
    expect(result.current.railWidth).toBe(COLLAPSED_RAIL_WIDTH)
  })

  it('every keyboard step lands exactly on a snap point', () => {
    saveRailWidth(DEFAULT_RAIL_WIDTH)
    // #1683: the declared detent set is now per-pin-count, so assert against
    // the set this hook was actually given — and check the full ladder too, via
    // a 4-pin hook that earns all of it.
    const { result } = renderHook(() => useRailResize({ narrow: false, pinnedCount: 3 }))
    const step = (key: string) =>
      act(() => {
        result.current.handleResizeKeyDown({
          key,
          preventDefault: () => {},
        } as unknown as React.KeyboardEvent<HTMLDivElement>)
      })
    // Walk all the way down and back; every stop must be a declared detent.
    for (let i = 0; i < RAIL_SNAP_POINTS.length + 2; i += 1) {
      step('ArrowLeft')
      expect(railSnapPointsForPins(3)).toContain(result.current.railWidth)
    }
    for (let i = 0; i < RAIL_SNAP_POINTS.length + 2; i += 1) {
      step('ArrowRight')
      expect(railSnapPointsForPins(3)).toContain(result.current.railWidth)
    }
  })

  it('#1683: the walk never leaves the pin count’s own detent set', () => {
    for (const pinnedCount of [0, 1, 2, 3, 4, 12]) {
      saveRailWidth(DEFAULT_RAIL_WIDTH)
      const { result, unmount } = renderHook(() =>
        useRailResize({ narrow: false, pinnedCount }),
      )
      const allowed = railSnapPointsForPins(pinnedCount)
      for (let i = 0; i < RAIL_SNAP_POINTS.length + 2; i += 1) {
        act(() => {
          result.current.handleResizeKeyDown({
            key: 'ArrowLeft',
            preventDefault: () => {},
          } as unknown as React.KeyboardEvent<HTMLDivElement>)
        })
        expect(allowed).toContain(result.current.railWidth)
      }
      for (let i = 0; i < RAIL_SNAP_POINTS.length + 2; i += 1) {
        act(() => {
          result.current.handleResizeKeyDown({
            key: 'ArrowRight',
            preventDefault: () => {},
          } as unknown as React.KeyboardEvent<HTMLDivElement>)
        })
        expect(allowed).toContain(result.current.railWidth)
      }
      unmount()
    }
  })
})
