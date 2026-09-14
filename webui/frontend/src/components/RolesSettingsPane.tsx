import { Component, useMemo, type ErrorInfo, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  fetchBlueprints,
  fetchCustomBlueprints,
  fetchRoles,
  type RoleDescriptor,
} from '../lib/api'
import { fetchTeamRosters } from '../lib/teamRosters'
import { loadAgentEdits } from '../lib/agentEdits'
import { normalizeAgentRole } from '../lib/agentRoles'

const MECHANISM_LABEL: Record<string, string> = {
  none: 'No wiring',
  intercept: 'Intercepts',
  parse: 'Parses',
  allow: 'Allow-all',
  implement: 'Implements',
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function listFromPayload(payload: unknown): unknown[] {
  if (Array.isArray(payload)) return payload
  const rec = asRecord(payload)
  return Array.isArray(rec?.data) ? rec.data : []
}

/** Drop incomplete /v1/roles/ rows instead of throwing in render. */
export function normalizeRoleDescriptor(raw: unknown): RoleDescriptor | null {
  const rec = asRecord(raw)
  if (!rec) return null
  const name = typeof rec.name === 'string' ? rec.name.trim() : ''
  if (!name) return null
  const aliases = Array.isArray(rec.aliases)
    ? rec.aliases.filter((alias): alias is string => typeof alias === 'string')
    : []
  return {
    name,
    label: typeof rec.label === 'string' ? rec.label : '',
    aliases,
    allow_all: Boolean(rec.allow_all),
    mechanism: typeof rec.mechanism === 'string' ? rec.mechanism : 'none',
    mechanism_detail: typeof rec.mechanism_detail === 'string' ? rec.mechanism_detail : '',
    css_class: typeof rec.css_class === 'string' ? rec.css_class : '',
  }
}

function rolesFromPayload(payload: unknown): RoleDescriptor[] {
  const out: RoleDescriptor[] = []
  for (const item of listFromPayload(payload)) {
    const role = normalizeRoleDescriptor(item)
    if (role) out.push(role)
  }
  return out
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message
  return 'Could not load roles.'
}

class RolesPaneErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Roles settings pane failed:', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="space-y-3" data-testid="settings-roles-pane">
          <p className="text-sm text-error">Could not load roles: {this.state.error.message}</p>
        </div>
      )
    }
    return this.props.children
  }
}

/** Settings pane: role implementation instances, their mechanism, and usage. */
function RolesSettingsPaneInner() {
  const rolesQuery = useQuery({ queryKey: ['settings-roles'], queryFn: fetchRoles, retry: 1 })
  const blueprintsQuery = useQuery({ queryKey: ['blueprints'], queryFn: fetchBlueprints, retry: 1 })
  const customQuery = useQuery({
    queryKey: ['custom-blueprints'],
    queryFn: fetchCustomBlueprints,
    retry: 1,
  })
  const rostersQuery = useQuery({ queryKey: ['team-rosters'], queryFn: fetchTeamRosters, retry: 1 })

  const roles = useMemo(() => rolesFromPayload(rolesQuery.data), [rolesQuery.data])

  const usage = useMemo(() => {
    const byRole = new Map<string, string[]>()
    const push = (role: string, label: string) => {
      const key = normalizeAgentRole(role)
      if (!byRole.has(key)) byRole.set(key, [])
      const list = byRole.get(key)!
      if (!list.includes(label)) list.push(label)
    }
    const rosters = listFromPayload(rostersQuery.data)
    for (const rawRoster of rosters) {
      const roster = asRecord(rawRoster)
      const members = Array.isArray(roster?.members) ? roster.members : []
      for (const rawMember of members) {
        const member = asRecord(rawMember)
        if (member?.kind === 'team') continue
        const role = typeof member?.role === 'string' ? member.role : 'default'
        const memberName = typeof member?.name === 'string' ? member.name : (typeof member?.id === 'string' ? member.id : 'agent')
        const rosterName = typeof roster?.name === 'string' ? roster.name : (typeof roster?.id === 'string' ? roster.id : 'roster')
        push(role, `${memberName} (${rosterName})`)
      }
    }
    const names = new Map<string, string>()
    for (const bp of [
      ...listFromPayload(blueprintsQuery.data),
      ...listFromPayload(customQuery.data),
    ]) {
      const rec = asRecord(bp)
      const id = typeof rec?.id === 'string' ? rec.id : ''
      const name = typeof rec?.name === 'string' ? rec.name : ''
      if (id && name) names.set(id, name)
    }
    try {
      const edits = loadAgentEdits()
      for (const [id, edit] of Object.entries(edits ?? {})) {
        if (edit?.role && edit.role !== 'default') {
          push(edit.role, names.get(id) ?? id)
        }
      }
    } catch {
      // Ignore local storage read issues
    }
    return byRole
  }, [rostersQuery.data, blueprintsQuery.data, customQuery.data])

  if (rolesQuery.isPending) {
    return (
      <p className="text-sm text-base-content/60" data-testid="settings-roles-pane">
        Loading roles…
      </p>
    )
  }

  if (rolesQuery.isError) {
    return (
      <div className="space-y-3" data-testid="settings-roles-pane">
        <p className="text-sm text-error">{errorMessage(rolesQuery.error)}</p>
      </div>
    )
  }

  return (
    <div className="space-y-3" data-testid="settings-roles-pane">
      <p className="text-xs text-base-content/60">
        Role implementation instances. Each role subclasses the Role contract with a
        mechanism — intercept (tool calls), parse (output), allow (mailbox scope),
        implement (does the work), or none. Usage lists roster assignments and local
        role overrides.
      </p>
      {roles.length === 0 ? (
        <p className="text-sm text-base-content/60">No roles returned.</p>
      ) : null}
      {roles.map((role) => {
        const users = usage.get(role.name) ?? []
        return (
          <div
            key={role.name}
            className="rounded-xl border border-base-300 p-3"
            data-testid={`role-row-${role.name}`}
          >
            <div className="flex flex-wrap items-center gap-2">
              {role.label ? (
                <span className={`os-agent-role-badge ${role.css_class}`}>{role.label}</span>
              ) : (
                <span className="text-sm font-semibold text-base-content/70">Worker (no badge)</span>
              )}
              <span className="badge badge-ghost badge-sm" data-testid={`role-mechanism-${role.name}`}>
                {MECHANISM_LABEL[role.mechanism] ?? role.mechanism}
              </span>
              {role.allow_all ? (
                <span className="badge badge-info badge-sm">allow-all</span>
              ) : null}
            </div>
            {role.mechanism_detail ? (
              <p className="mt-1 text-xs text-base-content/70">{role.mechanism_detail}</p>
            ) : null}
            <p className="mt-1 text-[11px] text-base-content/50">
              aliases: {role.aliases.join(', ') || '—'}
            </p>
            <div className="mt-2">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-base-content/50">
                Used by {users.length ? `(${users.length})` : ''}
              </p>
              {users.length ? (
                <ul className="mt-1 flex flex-wrap gap-1">
                  {users.map((u) => (
                    <li key={u} className="badge badge-outline badge-sm">
                      {u}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-base-content/50">No agents assigned.</p>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default function RolesSettingsPane() {
  return (
    <RolesPaneErrorBoundary>
      <RolesSettingsPaneInner />
    </RolesPaneErrorBoundary>
  )
}
