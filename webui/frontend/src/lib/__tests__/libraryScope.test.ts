import { describe, expect, it } from 'vitest'
import { filterLibraryByScope, LIBRARY_SCOPE_OPTIONS } from '../libraryScope'

describe('library scope filtering (#1311)', () => {
  const rows = [
    { id: 'a', scope: 'personal', title: 'Mine recipe' },
    { id: 'b', scope: 'team', title: 'Team recipe' },
    { id: 'c', scope: 'org', title: 'Org recipe' },
    { id: 'd', title: 'Legacy personal row' },
  ]

  it('labels Mine, Team, and Organisation', () => {
    expect(LIBRARY_SCOPE_OPTIONS.map((row) => row.label)).toEqual([
      'Mine',
      'Team',
      'Organisation',
    ])
  })

  it('keeps unspecified rows on Mine', () => {
    const mine = filterLibraryByScope(rows, 'personal')
    expect(mine.map((row) => row.id)).toEqual(['a', 'd'])
  })

  it('filters team and organisation separately', () => {
    expect(filterLibraryByScope(rows, 'team').map((row) => row.id)).toEqual(['b'])
    expect(filterLibraryByScope(rows, 'org').map((row) => row.id)).toEqual(['c'])
  })
})
