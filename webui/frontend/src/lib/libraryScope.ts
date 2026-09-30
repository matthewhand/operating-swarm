/** #1311 — Mine / Team / Organisation library scope. */

export type LibraryScope = 'personal' | 'team' | 'org'

export const LIBRARY_SCOPE_OPTIONS: ReadonlyArray<{ id: LibraryScope; label: string }> = [
  { id: 'personal', label: 'Mine' },
  { id: 'team', label: 'Team' },
  { id: 'org', label: 'Organisation' },
]

export function libraryScopeLabel(scope: LibraryScope): string {
  return LIBRARY_SCOPE_OPTIONS.find((row) => row.id === scope)?.label ?? 'Mine'
}

/** Rows without an explicit scope stay on the personal (Mine) catalog. */
export function filterLibraryByScope<T extends { scope?: string | null }>(
  items: readonly T[],
  scope: LibraryScope,
): T[] {
  return items.filter((item) => (item.scope || 'personal') === scope)
}
