/** #1399 — secret-free template catalog helpers for the SPA gallery / installer. */

import { isScopedSeatId, type CurrentAgent } from './currentAgent'
import type {
  AgentTemplatePack,
  GrokBotTemplate,
  TemplatePayload,
} from './api/templates'

export type TemplateCatalogSource = 'shipped' | 'seat' | 'file' | 'paste'

export interface TemplateCatalogItem {
  id: string
  name: string
  summary: string
  source: TemplateCatalogSource
  sourceLabel: string
  role: string
  memoryCount: number
  skillNames: string[]
  gettingStarted: string | null
  pack: TemplatePayload
}

/** File dogfood from #1398 — no secrets, matches tests/fixtures/agent_template_pack.json. */
export const SHIPPED_STOREFRONT_BEE: AgentTemplatePack = {
  schema: 1,
  kind: 'agent_template',
  agent_id: 'storefront-bee',
  profile: {
    display_name: 'Storefront Bee',
    description: 'Short storefront blurb for the rail and pack card.',
    title: 'Guide',
    role: 'support',
    avatar_shape: 'hexagon',
    avatar_color: '#f59e0b',
    avatar_path: '/avatars/bee/bee-profile-worker.svg',
  },
  memories: [
    {
      kind: 'profile',
      title: 'Voice',
      body: 'Keep answers short and point at the next step.',
    },
    {
      kind: 'log',
      title: 'Launch notes',
      body: 'Shipped the storefront card. No private links.',
    },
  ],
  skills: [
    {
      name: 'welcome-tour',
      description: 'Walk the first conversation.',
      instructions: 'Greet the operator and list three first steps.',
    },
  ],
  gettingStarted: { skill: 'welcome-tour' },
  routines: [],
  plugins: [],
}

/** File dogfood from tests/fixtures/swarm_engineer_template.json. No secrets. */
export const SHIPPED_SWARM_ENGINEER: AgentTemplatePack = {
  schema: 1,
  kind: 'agent_template',
  object: 'agent_template',
  profile: {
    display_name: 'Swarm Engineer',
    description: 'Implements fixes and opens PRs from GitHub issues.',
    title: 'Engineer',
    role: 'engineer',
    avatar_shape: 'square',
    avatar_color: '#2563eb',
    avatar_path: '/avatars/bee/bee-profile-worker.svg',
  },
  memories: [
    {
      kind: 'profile',
      title: 'Working style',
      body: 'Smallest correct fix. Quote Intent, Success, and Constraints. Leave fill-ins pending until the operator supplies them.',
    },
    {
      kind: 'log',
      title: 'Pack note',
      body: 'Recipe only. No private links, tokens, or host paths.',
    },
  ],
  skills: [
    {
      name: 'implement-issue',
      description: 'Investigate an issue, implement a fix, open a PR.',
      instructions: 'Read the issue. Implement only to Success. Open a PR. Do not merge. Leave {{owner_repo}} fill-ins for the operator.',
    },
  ],
  gettingStarted: { skill: 'implement-issue' },
  routines: [
    {
      key: 'github_issue_solver',
      name: 'GitHub Issue Solver (Issue → PR)',
      description: 'Investigate new issues in {{owner_repo}} and open a fix PR.',
      instruction: 'Investigate the issue in {{owner_repo}}, implement a fix, and open a pull request.',
      trigger: {
        kind: 'github_event',
        event_type: 'issues.opened',
        owner_repo: '{{owner_repo}}',
        filters: { exclude_authors: ['open-swarm[bot]'] },
      },
    },
  ],
  plugins: [
    {
      pluginId: 'web_search',
      name: 'web_search',
      description: 'Built-in catalog search tool.',
    },
  ],
}

/** #1311 org scopes are not on this branch. Browse stays one native scope. */
export const NATIVE_TEMPLATE_SCOPE_NOTE =
  'Native scope only. Org scopes wait on #1311.'

/** Backend Grok/template interop is file JSON. Share ids are not supported. */
export const TEMPLATE_SHARE_NOTE =
  'Import from a file. Share ids are not supported.'

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function isGrokTemplate(raw: unknown): raw is GrokBotTemplate {
  if (!isRecord(raw)) return false
  const kind = typeof raw.kind === 'string' ? raw.kind : ''
  const object = typeof raw.object === 'string' ? raw.object : ''
  return kind === 'grok_bot_template' || object === 'grok_bot_template'
}

export function isAgentTemplatePack(raw: unknown): raw is AgentTemplatePack {
  if (!isRecord(raw)) return false
  const kind = typeof raw.kind === 'string' ? raw.kind : ''
  const object = typeof raw.object === 'string' ? raw.object : ''
  return kind === 'agent_template' || object === 'agent_template'
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

export function templateDisplayName(pack: TemplatePayload): string {
  if (isGrokTemplate(pack)) {
    return asString(pack.name) || 'Untitled template'
  }
  if (isRecord(pack)) {
    const profile = isRecord(pack.profile) ? pack.profile : {}
    return (
      asString(profile.display_name) ||
      asString(pack.agent_id) ||
      'Untitled template'
    )
  }
  return 'Untitled template'
}

export function templateSummary(pack: TemplatePayload): string {
  if (isGrokTemplate(pack)) {
    return asString(pack.description)
  }
  if (isRecord(pack) && isRecord(pack.profile)) {
    return asString(pack.profile.description)
  }
  return ''
}

export function templateRole(pack: TemplatePayload): string {
  if (isGrokTemplate(pack)) return asString(pack.role)
  if (isRecord(pack) && isRecord(pack.profile)) return asString(pack.profile.role)
  return ''
}

function memoryRows(pack: TemplatePayload): unknown[] {
  if (!isRecord(pack)) return []
  return Array.isArray(pack.memories) ? pack.memories : []
}

function skillRows(pack: TemplatePayload): Array<{ name: string }> {
  if (!isRecord(pack) || !Array.isArray(pack.skills)) return []
  return pack.skills
    .filter(isRecord)
    .map((row) => ({ name: asString(row.name) }))
    .filter((row) => row.name)
}

export function templateGettingStarted(pack: TemplatePayload): string | null {
  if (!isRecord(pack)) return null
  const started = isRecord(pack.gettingStarted)
    ? pack.gettingStarted
    : isRecord(pack.getting_started)
      ? pack.getting_started
      : null
  const skill = started ? asString(started.skill) : ''
  return skill || null
}

export function catalogItemFromPack(
  pack: TemplatePayload,
  extras: Pick<TemplateCatalogItem, 'id' | 'source' | 'sourceLabel'>,
): TemplateCatalogItem {
  return {
    id: extras.id,
    name: templateDisplayName(pack),
    summary: templateSummary(pack),
    source: extras.source,
    sourceLabel: extras.sourceLabel,
    role: templateRole(pack),
    memoryCount: memoryRows(pack).length,
    skillNames: skillRows(pack).map((row) => row.name),
    gettingStarted: templateGettingStarted(pack),
    pack,
  }
}

export function shippedTemplateCatalog(): TemplateCatalogItem[] {
  return [
    catalogItemFromPack(SHIPPED_STOREFRONT_BEE, {
      id: 'shipped-storefront-bee',
      source: 'shipped',
      sourceLabel: 'Native',
    }),
    catalogItemFromPack(SHIPPED_SWARM_ENGINEER, {
      id: 'shipped-swarm-engineer',
      source: 'shipped',
      sourceLabel: 'Native',
    }),
  ]
}

export function filterTemplateItems(
  items: readonly TemplateCatalogItem[],
  query: string,
): TemplateCatalogItem[] {
  const needle = query.trim().toLowerCase()
  if (!needle) return [...items]
  return items.filter((item) => {
    const hay = [
      item.name,
      item.summary,
      item.role,
      item.sourceLabel,
      item.gettingStarted || '',
      ...item.skillNames,
    ]
      .join(' ')
      .toLowerCase()
    return hay.includes(needle)
  })
}

/** Bare seat id for import/export. Scoped team/remote ids are conversation scopes. */
export function installTargetFromCurrentAgent(agent: CurrentAgent | null | undefined): string {
  const id = agent?.id?.trim() || ''
  if (!id || isScopedSeatId(id)) return ''
  return id
}

export function parseTemplateJson(text: string): TemplatePayload {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    throw new Error('Template file is not valid JSON.')
  }
  if (!isRecord(parsed)) {
    throw new Error('Template must be a JSON object.')
  }
  return parsed
}

export function downloadTemplateJson(filename: string, payload: unknown): void {
  const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], {
    type: 'application/json',
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function countPhrase(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`
}

export function appliedSummary(applied: {
  memories?: number
  skills?: number
  routines?: number
  plugins?: number
} | null | undefined): string {
  const memories = applied?.memories ?? 0
  const skills = applied?.skills ?? 0
  const routines = applied?.routines ?? 0
  const plugins = applied?.plugins ?? 0
  return `Installed profile, ${countPhrase(memories, 'memory', 'memories')}, ${countPhrase(skills, 'skill')}, ${countPhrase(routines, 'routine')}, ${countPhrase(plugins, 'plugin')}.`
}

export function kickoffLine(skill: string | null | undefined): string {
  if (!skill) return 'Getting started: none'
  return `Getting started: ${skill} (pending kickoff)`
}

export interface ImportChecklist {
  agentId: string
  fillIns: Array<{ key: string; label: string }>
  connect: string[]
  gettingStarted: string | null
}

export function importChecklist(result: {
  agent_id?: string
  fill_ins_remaining?: unknown
  plugins_missing?: unknown
  template?: unknown
} | null | undefined): ImportChecklist {
  const fillIns: ImportChecklist['fillIns'] = []
  const remaining = result?.fill_ins_remaining
  if (Array.isArray(remaining)) {
    for (const item of remaining) {
      if (typeof item === 'string' && item.trim()) {
        fillIns.push({ key: item.trim(), label: item.trim() })
      } else if (item && typeof item === 'object' && !Array.isArray(item)) {
        const row = item as { key?: unknown; label?: unknown }
        const key = typeof row.key === 'string' ? row.key.trim() : ''
        if (!key) continue
        const label = typeof row.label === 'string' && row.label.trim() ? row.label.trim() : key
        fillIns.push({ key, label })
      }
    }
  }
  const connect = Array.isArray(result?.plugins_missing)
    ? result.plugins_missing.filter((item): item is string => typeof item === 'string' && item.trim() !== '')
    : []
  return {
    agentId: typeof result?.agent_id === 'string' ? result.agent_id : '',
    fillIns,
    connect,
    gettingStarted: templateGettingStarted(result?.template as TemplatePayload),
  }
}
