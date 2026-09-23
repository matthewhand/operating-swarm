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
  loadRailWidth,
  saveRailWidth,
} from '../../lib/railResize'
import { useRailResize } from '../sidebar/useRailResize'
import {
  isHerdrAgent,
  isCliRailAgent,
  isApiRailAgent,
  isBlueprintRailAgent,
  toSidebarCli,
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

  it('kind predicates agree with the mappers', () => {
    expect(isCliRailAgent({ kind: 'cli' })).toBe(true)
    expect(isApiRailAgent({ kind: 'api' })).toBe(true)
    expect(isApiRailAgent({ id: 'api_agent' })).toBe(true)
    expect(isBlueprintRailAgent({ kind: 'blueprint' })).toBe(true)
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

  it('expand restores the default width and persists', () => {
    saveRailWidth(COLLAPSED_RAIL_WIDTH)
    const { result } = renderHook(() => useRailResize({ narrow: false }))
    act(() => result.current.expandSidebar())
    expect(result.current.railWidth).toBe(DEFAULT_RAIL_WIDTH)
    expect(loadRailWidth()).toBe(DEFAULT_RAIL_WIDTH)
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
