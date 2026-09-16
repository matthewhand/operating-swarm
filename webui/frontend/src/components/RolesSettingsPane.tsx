import {
  Component,
  useEffect,
  useMemo,
  useState,
  type ErrorInfo,
  type ReactNode,
} from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  deleteRole as apiDeleteRole,
  fetchBlueprints,
  fetchCustomBlueprints,
  fetchRoles,
  type RoleDescriptor,
} from '../lib/api'
import { fetchTeamRosters } from '../lib/teamRosters'
import { AGENT_EDITS_CHANGED_EVENT, loadAgentEdits, saveAgentEdit } from '../lib/agentEdits'
import { normalizeAgentRole } from '../lib/agentRoles'
import {
  CUSTOM_ROLES_UPDATED_EVENT,
  deleteCustomRole,
  loadCustomRoles,
} from '../lib/customRoles'
import CreateRoleModal from './CreateRoleModal'

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
  const desc: RoleDescriptor = {
    name,
    label: typeof rec.label === 'string' ? rec.label : '',
    aliases,
    allow_all: Boolean(rec.allow_all),
    mechanism: typeof rec.mechanism === 'string' ? rec.mechanism : 'none',
    mechanism_detail: typeof rec.mechanism_detail === 'string' ? rec.mechanism_detail : '',
    css_class: typeof rec.css_class === 'string' ? rec.css_class : '',
  }
  if (rec.custom !== undefined) {
    desc.custom = Boolean(rec.custom)
  }
  return desc
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

interface RoleUser {
  agentId: string | null
  label: string
  canDetach: boolean
}

/** Settings pane: role implementation instances, their mechanism, custom role creation, and agent attachment. */
function RolesSettingsPaneInner() {
  const rolesQuery = useQuery({ queryKey: ['settings-roles'], queryFn: fetchRoles, retry: 1 })
  const blueprintsQuery = useQuery({ queryKey: ['blueprints'], queryFn: fetchBlueprints, retry: 1 })
  const customQuery = useQuery({
    queryKey: ['custom-blueprints'],
    queryFn: fetchCustomBlueprints,
    retry: 1,
  })
  const rostersQuery = useQuery({ queryKey: ['team-rosters'], queryFn: fetchTeamRosters, retry: 1 })

  const [customRoles, setCustomRoles] = useState<RoleDescriptor[]>(() => loadCustomRoles())
  const [editsRevision, setEditsRevision] = useState(0)
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [attachingRoleName, setAttachingRoleName] = useState<string | null>(null)

  useEffect(() => {
    const handleCustomRolesUpdated = () => {
      setCustomRoles(loadCustomRoles())
      rolesQuery.refetch()
    }
    const handleEditsChanged = () => {
      setEditsRevision((r) => r + 1)
    }
    window.addEventListener(CUSTOM_ROLES_UPDATED_EVENT, handleCustomRolesUpdated)
    window.addEventListener(AGENT_EDITS_CHANGED_EVENT, handleEditsChanged)
    return () => {
      window.removeEventListener(CUSTOM_ROLES_UPDATED_EVENT, handleCustomRolesUpdated)
      window.removeEventListener(AGENT_EDITS_CHANGED_EVENT, handleEditsChanged)
    }
  }, [rolesQuery])

  const roles = useMemo(() => {
    const serverRoles = rolesFromPayload(rolesQuery.data)
    const serverNames = new Set(serverRoles.map((r) => r.name))
    const merged = [...serverRoles]
    for (const cr of customRoles) {
      if (!serverNames.has(cr.name)) {
        merged.push(cr)
      }
    }
    return merged
  }, [rolesQuery.data, customRoles])

  const availableAgents = useMemo(() => {
    const items: { id: string; name: string }[] = []
    const seen = new Set<string>()
    for (const bp of [
      ...listFromPayload(blueprintsQuery.data),
      ...listFromPayload(customQuery.data),
    ]) {
      const rec = asRecord(bp)
      const id = typeof rec?.id === 'string' ? rec.id : ''
      const name = typeof rec?.name === 'string' ? rec.name : id
      if (id && !seen.has(id)) {
        seen.add(id)
        items.push({ id, name })
      }
    }
    return items.sort((a, b) => a.name.localeCompare(b.name))
  }, [blueprintsQuery.data, customQuery.data])

  const usage = useMemo(() => {
    // eslint-disable-next-line @typescript-eslint/no-unused-expressions
    editsRevision // Trigger dependency on edits revision change
    const byRole = new Map<string, RoleUser[]>()
    const push = (role: string, user: RoleUser) => {
      const key = normalizeAgentRole(role)
      if (!byRole.has(key)) byRole.set(key, [])
      const list = byRole.get(key)!
      if (!list.some((u) => u.label === user.label)) list.push(user)
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
        const memberId = typeof member?.id === 'string' ? member.id : null
        push(role, { agentId: memberId, label: `${memberName} (${rosterName})`, canDetach: false })
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
          push(edit.role, {
            agentId: id,
            label: names.get(id) ?? id,
            canDetach: true,
          })
        }
      }
    } catch {
      // Ignore local storage read issues
    }
    return byRole
  }, [rostersQuery.data, blueprintsQuery.data, customQuery.data, editsRevision])

  const handleAttachAgent = (roleName: string, agentId: string) => {
    if (!agentId) return
    saveAgentEdit(agentId, { role: roleName, roleOverridden: true })
    setAttachingRoleName(null)
    setEditsRevision((r) => r + 1)
  }

  const handleDetachAgent = (agentId: string | null) => {
    if (!agentId) return
    saveAgentEdit(agentId, { role: 'default', roleOverridden: true })
    setEditsRevision((r) => r + 1)
  }

  const handleDeleteRole = async (roleName: string) => {
    deleteCustomRole(roleName)
    try {
      await apiDeleteRole(roleName)
    } catch {
      /* ignore server error if offline or dev */
    }
    rolesQuery.refetch()
  }

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
    <div className="space-y-4" data-testid="settings-roles-pane">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-base-300/60 pb-3">
        <div>
          <h3 className="text-sm font-semibold text-base-content">Agent Roles</h3>
          <p className="text-xs text-base-content/60 max-w-xl mt-0.5">
            Role instances shape execution mechanisms — intercept (tool calls), parse
            (output), allow (mailbox scope), implement (work), or none. Create custom
            roles and attach them to any agent seat.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-primary btn-sm shrink-0 self-start sm:self-center"
          onClick={() => setIsCreateModalOpen(true)}
          data-testid="create-role-open-btn"
        >
          + Create Role
        </button>
      </div>

      {roles.length === 0 ? (
        <p className="text-sm text-base-content/60">No roles returned.</p>
      ) : null}

      <div className="space-y-3">
        {roles.map((role) => {
          const users = usage.get(role.name) ?? []
          const isAttaching = attachingRoleName === role.name

          return (
            <div
              key={role.name}
              className="rounded-xl border border-base-300 p-3 relative bg-base-100/50"
              data-testid={`role-row-${role.name}`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  {role.label ? (
                    <span className={`os-agent-role-badge ${role.css_class}`}>{role.label}</span>
                  ) : (
                    <span className="text-sm font-semibold text-base-content/70">
                      Worker (no badge)
                    </span>
                  )}
                  <span
                    className="badge badge-ghost badge-sm"
                    data-testid={`role-mechanism-${role.name}`}
                  >
                    {MECHANISM_LABEL[role.mechanism] ?? role.mechanism}
                  </span>
                  {role.allow_all ? (
                    <span className="badge badge-info badge-sm">allow-all</span>
                  ) : null}
                  {role.custom ? (
                    <span
                      className="badge badge-secondary badge-sm"
                      data-testid={`role-custom-badge-${role.name}`}
                    >
                      custom
                    </span>
                  ) : null}
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className="btn btn-ghost btn-xs text-primary font-medium"
                    onClick={() =>
                      setAttachingRoleName(isAttaching ? null : role.name)
                    }
                    data-testid={`role-attach-btn-${role.name}`}
                  >
                    {isAttaching ? 'Cancel' : '+ Attach to agent'}
                  </button>

                  {role.custom ? (
                    <button
                      type="button"
                      className="btn btn-ghost btn-xs text-error"
                      onClick={() => handleDeleteRole(role.name)}
                      title="Delete custom role"
                      data-testid={`role-delete-${role.name}`}
                    >
                      Delete
                    </button>
                  ) : null}
                </div>
              </div>

              {isAttaching ? (
                <div
                  className="mt-2.5 p-2 bg-base-200/60 rounded-lg flex items-center gap-2"
                  data-testid={`role-attach-picker-${role.name}`}
                >
                  <span className="text-xs font-medium text-base-content/70">
                    Attach to agent:
                  </span>
                  <select
                    className="select select-bordered select-xs flex-1"
                    defaultValue=""
                    onChange={(e) => handleAttachAgent(role.name, e.target.value)}
                    data-testid={`role-attach-select-${role.name}`}
                  >
                    <option value="" disabled>
                      Choose an agent…
                    </option>
                    {availableAgents.map((agent) => (
                      <option key={agent.id} value={agent.id}>
                        {agent.name} ({agent.id})
                      </option>
                    ))}
                  </select>
                </div>
              ) : null}

              {role.mechanism_detail ? (
                <p className="mt-1.5 text-xs text-base-content/70">{role.mechanism_detail}</p>
              ) : null}
              <p className="mt-1 text-[11px] text-base-content/50">
                aliases: {role.aliases.join(', ') || '—'}
              </p>

              <div className="mt-2 pt-2 border-t border-base-200">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-base-content/50">
                  Used by {users.length ? `(${users.length})` : ''}
                </p>
                {users.length ? (
                  <ul className="mt-1 flex flex-wrap gap-1.5" data-testid={`role-users-${role.name}`}>
                    {users.map((u) => (
                      <li
                        key={u.label}
                        className="badge badge-outline badge-sm gap-1 py-2 pl-2 pr-1"
                      >
                        <span>{u.label}</span>
                        {u.canDetach ? (
                          <button
                            type="button"
                            className="btn btn-ghost btn-circle btn-xs text-base-content/50 hover:text-error w-3.5 h-3.5 min-h-0 text-[10px] leading-none"
                            onClick={() => handleDetachAgent(u.agentId)}
                            title={`Detach ${role.name} role`}
                            aria-label={`Detach role from ${u.label}`}
                            data-testid={`detach-role-${role.name}-${u.agentId}`}
                          >
                            ×
                          </button>
                        ) : null}
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

      <CreateRoleModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
      />
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
