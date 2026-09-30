/**
 * Search-palette events and option types, split from the palette component
 * so the rail can open search without pulling the palette module into the
 * initial chat chunk (#1443).
 */

export const SEARCH_PALETTE_TABS = [
  'All',
  'Messages',
  'Agents',
  'Teams',
  'Files',
  'Links',
  'Routines',
  'Actions',
  'Settings',
] as const

export type SearchPaletteTab = (typeof SEARCH_PALETTE_TABS)[number]

/**
 * #1222: operator-facing label for a search tab. The tab identifier stays
 * `Teams` (a stable code/data key); only the rendered label is rebranded.
 */
export function searchPaletteTabLabel(tab: SearchPaletteTab): string {
  return tab === 'Teams' ? 'Rigs' : tab
}

export const OPEN_SEARCH_EVENT = 'swarm:open-search'

/**
 * #549: a hidden rail row the palette cannot derive from `/v1/blueprints/`.
 *
 * The rail badge counts **agents + teams + remotes**, assembled from blueprints,
 * rosters, remotes, cli and herdr feeds — but the palette's universe is
 * `railSeatAgents(blueprints)`, i.e. recipes only. So "Hidden Bots 3" could
 * open on an empty list whenever the hidden things were a team, a remote or a
 * CLI/herdr seat. The rail knows those rows, so it hands them over.
 */
export interface HiddenRailRow {
  /** The rail/pin id — a bare agent id, or `team:<id>` / `remote:<id>`. */
  id: string
  name: string
  description?: string
  href?: string
  avatarPath?: string | null
  tab?: 'Agents' | 'Teams'
}

export interface SearchPaletteOptions {
  filterHidden?: boolean
  tab?: SearchPaletteTab
  query?: string
  /**
   * #549: the **reconciled** hidden ids the rail badge counted (local storage
   * plus server prefs). The palette used to seed from localStorage alone, so
   * the count could exceed the list for an id hidden only on the server.
   */
  hiddenIds?: string[]
  /** #549: non-catalog hidden rows — teams, remotes, herdr and CLI seats. */
  hiddenRows?: HiddenRailRow[]
}

export function openSearchPalette(options?: SearchPaletteOptions): void {
  window.dispatchEvent(new CustomEvent(OPEN_SEARCH_EVENT, { detail: options }))
}
