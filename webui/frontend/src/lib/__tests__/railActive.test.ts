import { describe, expect, it } from 'vitest'
import {
  activeRailId,
  activeRailIdFromParams,
  isHerdrRowActive,
  railSelectionFromParams,
  railSelectionKind,
} from '../railActive'

const params = (query: string) => new URLSearchParams(query.replace(/^\?/, ''))

describe('railActive (#542)', () => {
  it('resolves a team scope to the team: pin id shape, not the bare id', () => {
    const selection = railSelectionFromParams(params('?team=research'))
    expect(selection.teamId).toBe('research')
    expect(railSelectionKind(selection)).toBe('team')
    // The pin/row ids are stored as `team:<id>` while the query param is bare,
    // so a plain equality would silently never match.
    expect(activeRailId(selection)).toBe('team:research')
    expect(activeRailId(selection)).not.toBe('research')
  })

  it('resolves a remote scope to the remote: pin id shape', () => {
    const selection = railSelectionFromParams(params('?remote=herdr'))
    expect(railSelectionKind(selection)).toBe('remote')
    expect(activeRailId(selection)).toBe('remote:herdr')
  })

  it('resolves a seat scope to the blueprint id', () => {
    const selection = railSelectionFromParams(params('?blueprint=codey'))
    expect(railSelectionKind(selection)).toBe('seat')
    expect(activeRailId(selection)).toBe('codey')
  })

  it('gives team precedence over remote over blueprint', () => {
    // A team/remote selection may also carry a stale `?blueprint=`; precedence
    // is what keeps the team row active instead of a leftover seat row.
    expect(activeRailIdFromParams(params('?team=t1&remote=r1&blueprint=codey'))).toBe('team:t1')
    expect(activeRailIdFromParams(params('?remote=r1&blueprint=codey'))).toBe('remote:r1')
    expect(activeRailIdFromParams(params('?blueprint=codey'))).toBe('codey')
  })

  it('never returns an empty id — no scope falls back to the support seat', () => {
    // Matches `defaultBlueprintId`, which is what the seat scope has always
    // resolved to. An empty id would make `Boolean(activeRail && ...)` guards
    // silently disable every highlight again.
    expect(activeRailIdFromParams(params(''))).not.toBe('')
    expect(activeRailIdFromParams(null)).not.toBe('')
  })

  it('ignores blank and whitespace-only params instead of selecting a blank scope', () => {
    const selection = railSelectionFromParams(params('?team=&remote=%20&blueprint=codey'))
    expect(selection.teamId).toBe('')
    expect(selection.remoteId).toBe('')
    expect(railSelectionKind(selection)).toBe('seat')
  })

  it('tolerates a missing search-params object', () => {
    expect(() => railSelectionFromParams(undefined)).not.toThrow()
    expect(railSelectionKind(railSelectionFromParams(undefined))).toBe('seat')
  })

  it('does not claim herdr rows can be active — they have no URL representation', () => {
    // Documented exclusion: every herdr row shares `/teams/#herdr-members`, so
    // marking them from the URL would light them all up at once.
    expect(isHerdrRowActive()).toBe(false)
  })
})
