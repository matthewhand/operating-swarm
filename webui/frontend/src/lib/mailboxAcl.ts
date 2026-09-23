import { apiDelete, apiGet, apiPut, type AgentRole } from './api'

/** Entry targets documented by GET /v1/mailbox-acl/ (REQ-162). */
export type MailboxAclEntryKind = 'agent' | 'team' | 'role' | 'section'
export type MailboxAclMode = 'whitelist' | 'blacklist'
export type MailboxAclScope = 'agent' | 'role'
export type MailboxAclSource = 'agent' | 'role' | 'default'

export const MAILBOX_ACL_ENTRY_KINDS: { kind: MailboxAclEntryKind; label: string; hint: string }[] =
  [
    { kind: 'agent', label: 'Agent', hint: 'A catalogued rail or roster agent id.' },
    { kind: 'team', label: 'Team', hint: 'A team roster id — every member of that team.' },
    { kind: 'role', label: 'Role', hint: 'A canonical role (support, gate, skeptic, CoS, …).' },
    { kind: 'section', label: 'Section', hint: 'Members of a CoS rail section.' },
  ]

export const MAILBOX_ACL_ROLE_OPTIONS: { value: AgentRole; label: string }[] = [
  { value: 'default', label: 'default' },
  { value: 'support', label: 'support' },
  { value: 'gate', label: 'gate' },
  { value: 'skeptic', label: 'skeptic' },
  { value: 'chief_of_staff', label: 'chief_of_staff' },
  { value: 'engineer', label: 'engineer' },
  { value: 'suggestions', label: 'suggestions' },
]

export interface MailboxAclEntry {
  kind: MailboxAclEntryKind
  id: string
}

export interface MailboxAcl {
  object: 'mailbox_acl'
  scope: MailboxAclScope
  id: string
  role: AgentRole
  source: MailboxAclSource
  inherited: boolean
  mode: MailboxAclMode
  allow_all: boolean
  entries: MailboxAclEntry[]
  entry_kinds: { kind: MailboxAclEntryKind; description: string }[]
}

export interface MailboxAclStore {
  object: 'mailbox_acl_store'
  schema: number
  agents: Record<string, { mode: MailboxAclMode; entries: MailboxAclEntry[] }>
  roles: Record<string, { mode: MailboxAclMode; entries: MailboxAclEntry[] }>
  entry_kinds: { kind: MailboxAclEntryKind; description: string }[]
}

const ENTRY_KINDS = new Set<MailboxAclEntryKind>(['agent', 'team', 'role', 'section'])

export function isAllowAllRole(role: string | null | undefined): boolean {
  const key = String(role || '').trim().toLowerCase()
  return key === 'support' || key === 'helper' || key === 'chief_of_staff' || key === 'cos' || key === 'chief'
}

export function defaultMailboxAcl(id: string, role: AgentRole, scope: MailboxAclScope): MailboxAcl {
  const allowAll = isAllowAllRole(role)
  return {
    object: 'mailbox_acl',
    scope,
    id: scope === 'role' ? role : id,
    role,
    source: 'default',
    inherited: true,
    mode: allowAll ? 'whitelist' : 'blacklist',
    allow_all: allowAll,
    entries: [],
    entry_kinds: MAILBOX_ACL_ENTRY_KINDS.map((row) => ({
      kind: row.kind,
      description: row.hint,
    })),
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

export function parseMailboxAclEntry(raw: unknown): MailboxAclEntry | null {
  const rec = asRecord(raw)
  if (!rec) return null
  const kind = String(rec.kind || 'agent').trim().toLowerCase()
  if (!ENTRY_KINDS.has(kind as MailboxAclEntryKind)) return null
  const id = String(rec.id || rec.name || '').trim()
  if (!id) return null
  return { kind: kind as MailboxAclEntryKind, id }
}

export function parseMailboxAcl(
  raw: unknown,
  fallback: MailboxAcl,
): MailboxAcl {
  const rec = asRecord(raw)
  if (!rec || rec.object !== 'mailbox_acl') return fallback
  const mode = rec.mode === 'whitelist' || rec.mode === 'blacklist' ? rec.mode : fallback.mode
  const scope: MailboxAclScope = rec.scope === 'role' ? 'role' : 'agent'
  const source: MailboxAclSource =
    rec.source === 'agent' || rec.source === 'role' || rec.source === 'default'
      ? rec.source
      : fallback.source
  const entries = Array.isArray(rec.entries)
    ? rec.entries.map(parseMailboxAclEntry).filter((row): row is MailboxAclEntry => row !== null)
    : []
  const role = (typeof rec.role === 'string' && rec.role ? rec.role : fallback.role) as AgentRole
  return {
    object: 'mailbox_acl',
    scope,
    id: String(rec.id || fallback.id),
    role,
    source,
    inherited: rec.inherited === true,
    mode,
    allow_all: rec.allow_all === true,
    entries,
    entry_kinds: fallback.entry_kinds,
  }
}

export async function fetchMailboxAcl(
  agentId: string,
  role?: string,
): Promise<MailboxAcl> {
  const fallback = defaultMailboxAcl(agentId, (role || 'default') as AgentRole, 'agent')
  const query = role ? `?role=${encodeURIComponent(role)}` : ''
  try {
    const raw = await apiGet<unknown>(`/v1/mailbox-acl/agents/${encodeURIComponent(agentId)}/${query}`)
    return parseMailboxAcl(raw, fallback)
  } catch {
    return fallback
  }
}

export async function fetchMailboxAclRole(role: AgentRole): Promise<MailboxAcl> {
  const fallback = defaultMailboxAcl(role, role, 'role')
  try {
    const raw = await apiGet<unknown>(`/v1/mailbox-acl/roles/${encodeURIComponent(role)}/`)
    return parseMailboxAcl(raw, fallback)
  } catch {
    return fallback
  }
}

export async function saveMailboxAcl(
  scope: MailboxAclScope,
  id: string,
  body: { mode: MailboxAclMode; entries: MailboxAclEntry[]; role?: string },
): Promise<MailboxAcl> {
  const fallback = defaultMailboxAcl(id, (body.role || 'default') as AgentRole, scope)
  const path =
    scope === 'role'
      ? `/v1/mailbox-acl/roles/${encodeURIComponent(id)}/`
      : `/v1/mailbox-acl/agents/${encodeURIComponent(id)}/`
  const raw = await apiPut<unknown>(path, body)
  return parseMailboxAcl(raw, fallback)
}

export async function resetMailboxAcl(
  scope: MailboxAclScope,
  id: string,
  role?: string,
): Promise<MailboxAcl> {
  const path =
    scope === 'role'
      ? `/v1/mailbox-acl/roles/${encodeURIComponent(id)}/`
      : `/v1/mailbox-acl/agents/${encodeURIComponent(id)}/`
  const query = scope === 'agent' && role ? `?role=${encodeURIComponent(role)}` : ''
  await apiDelete(`${path}${query}`)
  return scope === 'role' ? fetchMailboxAclRole(id as AgentRole) : fetchMailboxAcl(id, role)
}
