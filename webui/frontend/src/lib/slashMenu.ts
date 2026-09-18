/**
 * Data structures, catalog definitions, and recency/filter helpers
 * for the Composer slash popup (REQ-169).
 */

export type SlashItemKind = 'action' | 'skill' | 'cli'

/** #641: `slash_commands` row from GET /v1/cli-agents/ — provider-declared. */
export interface CliSlashCommandSpec {
  name: string
  description?: string
  available?: boolean
  unavailable_reason?: string
}

export interface SlashItem {
  id: string
  kind: SlashItemKind
  name: string
  command: string
  title: string
  description: string
  iconName?: string
  /** #641: set when the CLI cannot run this command non-interactively. */
  unavailableReason?: string
}

export const RECENT_SLASH_STORAGE_KEY = 'open_swarm_recent_slash_commands'
const MAX_RECENT_ITEMS = 10

export const DEFAULT_ACTIONS: SlashItem[] = [
  {
    id: 'compact',
    kind: 'action',
    name: 'compact',
    command: '/compact',
    title: 'Compact',
    description: 'Summarise conversation backlog into nested summary blocks',
    iconName: 'Layers',
  },
  {
    id: 'help',
    kind: 'action',
    name: 'help',
    command: '/help',
    title: 'Help',
    description: 'List available slash commands and assistant capabilities',
    iconName: 'HelpCircle',
  },
  {
    id: 'model',
    kind: 'action',
    name: 'model',
    command: '/model',
    title: 'Model',
    description: 'View current LLM profile or override settings',
    iconName: 'Cpu',
  },
  {
    id: 'clear',
    kind: 'action',
    name: 'clear',
    command: '/clear',
    title: 'Clear',
    description: 'Clear conversation context or reset current turn',
    iconName: 'Trash2',
  },
  {
    id: 'approval',
    kind: 'action',
    name: 'approval',
    command: '/approval',
    title: 'Approval',
    description: 'Toggle or display auto-approval mode',
    iconName: 'Shield',
  },
  {
    id: 'history',
    kind: 'action',
    name: 'history',
    command: '/history',
    title: 'History',
    description: 'Display session command and file history',
    iconName: 'History',
  },
]

export const DEFAULT_SKILLS: SlashItem[] = [
  {
    id: 'conventional-commit',
    kind: 'skill',
    name: 'conventional-commit',
    command: '/skill conventional-commit',
    title: 'Conventional Commit',
    description: 'Format commits following Conventional Commits specification',
    iconName: 'GitCommit',
  },
  {
    id: 'counting-lines',
    kind: 'skill',
    name: 'counting-lines',
    command: '/skill counting-lines',
    title: 'Counting Lines',
    description: 'Count non-blank lines in files using bundled count tool',
    iconName: 'FileText',
  },
  {
    id: 'reviewing-code',
    kind: 'skill',
    name: 'reviewing-code',
    command: '/skill reviewing-code',
    title: 'Reviewing Code',
    description: 'Review diffs for bugs, security vulnerabilities, and test coverage',
    iconName: 'CheckSquare',
  },
  {
    id: 'support-session-ownership',
    kind: 'skill',
    name: 'support-session-ownership',
    command: '/skill support-session-ownership',
    title: 'Support Session Ownership',
    description: 'Session continuity and thread ownership protocols',
    iconName: 'LifeBuoy',
  },
  {
    id: 'writing-changelog',
    kind: 'skill',
    name: 'writing-changelog',
    command: '/skill writing-changelog',
    title: 'Writing Changelog',
    description: 'Generate Keep a Changelog formatted changelog entries',
    iconName: 'ListPlus',
  },
]

/**
 * Builds the complete slash catalog by combining default actions with default
 * skills, any dynamic skills discovered from the backend, and — #641 — the
 * selected CLI seat's own declared commands from the cli-agents catalog.
 */
export function buildSlashCatalog(
  dynamicSkills?: { name: string; description?: string }[],
  cliSlashCommands?: CliSlashCommandSpec[],
): SlashItem[] {
  const items: SlashItem[] = [...DEFAULT_ACTIONS]
  const seenSkills = new Set<string>()

  // Add dynamic skills first if available
  if (dynamicSkills && dynamicSkills.length > 0) {
    for (const s of dynamicSkills) {
      if (!s.name || seenSkills.has(s.name)) continue
      seenSkills.add(s.name)
      const existing = DEFAULT_SKILLS.find((def) => def.name === s.name)
      items.push({
        id: s.name,
        kind: 'skill',
        name: s.name,
        command: `/skill ${s.name}`,
        title: existing ? existing.title : formatSkillTitle(s.name),
        description: s.description || existing?.description || `Skill: ${s.name}`,
        iconName: existing?.iconName || 'Sparkles',
      })
    }
  }

  // Add remaining default skills
  for (const s of DEFAULT_SKILLS) {
    if (!seenSkills.has(s.name)) {
      seenSkills.add(s.name)
      items.push(s)
    }
  }

  // #641: the CLI seat's own declared commands (data-driven, never hardcoded
  // in JSX). A command whose verb already exists as a default action replaces
  // it — the CLI-native row is the honest one for a CLI seat.
  for (const cmd of cliSlashCommands ?? []) {
    const name = (cmd.name || '').trim().replace(/^\//, '')
    if (!name) continue
    const command = `/${name}`
    const existingIdx = items.findIndex(
      (entry) => entry.kind === 'action' && entry.command === command,
    )
    if (existingIdx !== -1) items.splice(existingIdx, 1)
    items.push({
      id: `cli-${name}`,
      kind: 'cli',
      name,
      command,
      title: formatSkillTitle(name),
      description:
        cmd.available === false
          ? cmd.unavailable_reason || 'Not available in non-interactive mode'
          : cmd.description || formatSkillTitle(name),
      iconName: 'Terminal',
      unavailableReason: cmd.available === false ? cmd.unavailable_reason || 'Not available in non-interactive mode' : undefined,
    })
  }

  return items
}

function formatSkillTitle(name: string): string {
  return name
    .split('-')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

/** Retrieve list of recently used slash item IDs. */
export function getRecentSlashIds(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_SLASH_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      return parsed.filter((x): x is string => typeof x === 'string')
    }
  } catch {
    // Ignore parse errors or unavailable localStorage
  }
  return []
}

/** Record a used slash item ID to the top of recency. */
export function recordRecentSlashId(id: string): void {
  if (!id) return
  try {
    const recents = getRecentSlashIds().filter((existing) => existing !== id)
    recents.unshift(id)
    if (recents.length > MAX_RECENT_ITEMS) {
      recents.length = MAX_RECENT_ITEMS
    }
    localStorage.setItem(RECENT_SLASH_STORAGE_KEY, JSON.stringify(recents))
  } catch {
    // Ignore storage quota or access issues
  }
}

/** Clear recency store (useful for tests). */
export function clearRecentSlashIds(): void {
  try {
    localStorage.removeItem(RECENT_SLASH_STORAGE_KEY)
  } catch {
    // Ignore
  }
}

/**
 * Filter and sort slash items based on user query and recent history.
 * - If query is empty: recent items come first, followed by remaining items
 *   alphabetically by title within their kind (Action / Skill).
 * - If query is non-empty: items matching query by name, title, command, or description,
 *   with exact starts-with matches and recents ranked higher.
 */
export function filterSlashItems(
  items: SlashItem[],
  rawQuery: string,
  recentIds: string[] = [],
): SlashItem[] {
  const query = rawQuery.replace(/^\//, '').trim().toLowerCase()

  if (!query) {
    // Empty query: recent items first (in order of recency)
    const recentMap = new Map<string, number>()
    recentIds.forEach((id, index) => recentMap.set(id, index))

    const recents: SlashItem[] = []
    const actions: SlashItem[] = []
    const skills: SlashItem[] = []
    const cliCommands: SlashItem[] = []

    for (const item of items) {
      if (recentMap.has(item.id)) {
        recents.push(item)
      } else if (item.kind === 'action') {
        actions.push(item)
      } else if (item.kind === 'cli') {
        cliCommands.push(item)
      } else {
        skills.push(item)
      }
    }

    // Sort recents by recency index
    recents.sort((a, b) => (recentMap.get(a.id) ?? 0) - (recentMap.get(b.id) ?? 0))
    // Sort rest alphabetically
    actions.sort((a, b) => a.title.localeCompare(b.title))
    skills.sort((a, b) => a.title.localeCompare(b.title))
    cliCommands.sort((a, b) => a.title.localeCompare(b.title))

    return [...recents, ...actions, ...cliCommands, ...skills]
  }

  // Filter matching items
  const matched = items.filter((item) => {
    const nameMatch = item.name.toLowerCase().includes(query)
    const titleMatch = item.title.toLowerCase().includes(query)
    const cmdMatch = item.command.toLowerCase().includes(query)
    const descMatch = item.description.toLowerCase().includes(query)
    return nameMatch || titleMatch || cmdMatch || descMatch
  })

  // Rank matches
  matched.sort((a, b) => {
    const aCmdStarts = a.name.toLowerCase().startsWith(query) || a.command.replace(/^\//, '').toLowerCase().startsWith(query)
    const bCmdStarts = b.name.toLowerCase().startsWith(query) || b.command.replace(/^\//, '').toLowerCase().startsWith(query)
    if (aCmdStarts && !bCmdStarts) return -1
    if (!aCmdStarts && bCmdStarts) return 1

    const aRecentIdx = recentIds.indexOf(a.id)
    const bRecentIdx = recentIds.indexOf(b.id)
    const aIsRecent = aRecentIdx !== -1
    const bIsRecent = bRecentIdx !== -1

    if (aIsRecent && !bIsRecent) return -1
    if (!aIsRecent && bIsRecent) return 1
    if (aIsRecent && bIsRecent) return aRecentIdx - bRecentIdx

    return a.title.localeCompare(b.title)
  })

  return matched
}

export interface SlashGroup {
  label: string
  items: SlashItem[]
}

/**
 * Group filtered slash items for sectioned display.
 */
export function groupSlashItems(
  items: SlashItem[],
  rawQuery: string,
  recentIds: string[] = [],
): SlashGroup[] {
  const query = rawQuery.replace(/^\//, '').trim()

  if (!query) {
    const recentSet = new Set(recentIds)
    const recents: SlashItem[] = []
    const actions: SlashItem[] = []
    const skills: SlashItem[] = []
    const cliCommands: SlashItem[] = []

    for (const item of items) {
      if (recentSet.has(item.id)) {
        recents.push(item)
      } else if (item.kind === 'action') {
        actions.push(item)
      } else if (item.kind === 'cli') {
        cliCommands.push(item)
      } else {
        skills.push(item)
      }
    }

    const groups: SlashGroup[] = []
    if (recents.length > 0) {
      groups.push({ label: 'Recent', items: recents })
    }
    if (actions.length > 0) {
      groups.push({ label: 'Actions', items: actions })
    }
    if (cliCommands.length > 0) {
      groups.push({ label: 'CLI Commands', items: cliCommands })
    }
    if (skills.length > 0) {
      groups.push({ label: 'Skills', items: skills })
    }
    return groups
  }

  // When filtered by query, group by kind
  const actions = items.filter((item) => item.kind === 'action')
  const skills = items.filter((item) => item.kind === 'skill')
  const cliCommands = items.filter((item) => item.kind === 'cli')

  const groups: SlashGroup[] = []
  if (actions.length > 0) {
    groups.push({ label: 'Actions', items: actions })
  }
  if (cliCommands.length > 0) {
    groups.push({ label: 'CLI Commands', items: cliCommands })
  }
  if (skills.length > 0) {
    groups.push({ label: 'Skills', items: skills })
  }
  return groups
}
