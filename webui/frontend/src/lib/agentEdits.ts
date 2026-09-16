/**
 * Per-agent editor overrides (REQ-58).
 *
 * Agents in the rail are seats. Each seat can be assigned a catalog blueprint,
 * a display name, a role badge, and an optional LLM override. Persistence is
 * localStorage until an agent-edit API exists — same best-effort pattern as
 * hostname / hidden / pinned.
 *
 * Chat identity stays the agent id (`?blueprint=<agentId>`). The assigned
 * blueprint is what the websocket / run uses.
 */

import type { AgentRole, BlueprintWorkflow } from './api'
import {
  normalizeInferenceList,
  serializeInferenceList,
  type InferenceSeat,
} from './inferenceList'

export const AGENT_EDITS_KEY = 'swarm_agent_edits'
export const AGENT_EDITS_CHANGED_EVENT = 'swarm:agent-edits-changed'

const AGENT_ROLES: readonly AgentRole[] = [
  'default',
  'support',
  'gate',
  'skeptic',
  'chief_of_staff',
  'engineer',
  'suggestions',
]

function isAgentRole(value: unknown): value is AgentRole {
  return typeof value === 'string' && (AGENT_ROLES as readonly string[]).includes(value)
}

export interface AgentEdit {
  name?: string
  role?: AgentRole
  /**
   * True after the operator changes Role in the agent editor.
   * Re-picking a blueprint re-applies that blueprint's default role unless
   * this flag is set (REQ-75).
   */
  roleOverridden?: boolean
  blueprintId?: string
  /** Optional openai-agents workflow hint copied from the assigned blueprint. */
  workflow?: BlueprintWorkflow
  llmOverride?: string
  folder?: string
  /** Last known git branch for the bound Folder (navbar subtitle, #65). */
  gitBranch?: string
  /** REQ-166 Phase 0 — GitHub repo bind (chrome + local persist; no checkout). */
  githubRepo?: string
  /** REQ-166 Phase 0 — worktree scale-out toggle (chrome only; stays off until Phase 3). */
  workspacesEnabled?: boolean
  command?: string
  cliOverride?: string
  profileOverride?: string
  /** REQ-69 ordered inference seats (`llm:…` / `cli:…` / `remote:…`). Empty = Settings default. */
  inferenceList?: string[]
  /** REQ-212 attached SKILL.md names for API / Blueprint-backed seats. */
  skills?: string[]
  /** Issue #180: optional remote serve endpoint (host/port/auth_env/box). */
  remote?: {
    host?: string
    port?: number
    username?: string
    password_env?: string
    box?: string
  }
}

export type AgentEditMap = Record<string, AgentEdit>

function readMap(): AgentEditMap {
  try {
    const raw = localStorage.getItem(AGENT_EDITS_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return parsed as AgentEditMap
  } catch {
    return {}
  }
}

function writeMap(map: AgentEditMap): void {
  try {
    localStorage.setItem(AGENT_EDITS_KEY, JSON.stringify(map))
  } catch {
    /* persistence is best-effort */
  }
}

function emitChange(agentId: string): void {
  try {
    window.dispatchEvent(
      new CustomEvent(AGENT_EDITS_CHANGED_EVENT, { detail: { agentId } }),
    )
  } catch {
    /* jsdom / detached window */
  }
}

export function loadAgentEdits(): AgentEditMap {
  return readMap()
}

export function loadAgentEdit(agentId: string): AgentEdit {
  if (!agentId) return {}
  return readMap()[agentId] ?? {}
}

export function saveAgentEdit(agentId: string, patch: AgentEdit): AgentEdit {
  if (!agentId) return {}
  const map = readMap()
  const current = map[agentId] ?? {}
  const next: AgentEdit = { ...current }

  if (patch.name !== undefined) {
    const name = patch.name.trim()
    if (name) next.name = name
    else delete next.name
  }
  if (patch.role !== undefined) {
    const role = isAgentRole(patch.role) ? patch.role : 'default'
    if (role !== 'default') next.role = role
    else delete next.role
  }
  if (patch.roleOverridden !== undefined) {
    if (patch.roleOverridden) next.roleOverridden = true
    else delete next.roleOverridden
  }
  if (patch.workflow !== undefined) {
    const workflow = patch.workflow
    if (workflow === 'handoff' || workflow === 'as_tool') next.workflow = workflow
    else delete next.workflow
  }
  if (patch.blueprintId !== undefined) {
    const blueprintId = patch.blueprintId.trim()
    if (blueprintId && blueprintId !== agentId) next.blueprintId = blueprintId
    else delete next.blueprintId
  }
  if (patch.llmOverride !== undefined) {
    const llm = patch.llmOverride.trim()
    if (llm) next.llmOverride = llm
    else delete next.llmOverride
  }
  if (patch.folder !== undefined) {
    const folder = patch.folder.trim()
    const prev = (current.folder || '').trim()
    if (folder) next.folder = folder
    else delete next.folder
    if (folder !== prev && patch.gitBranch === undefined) delete next.gitBranch
  }
  if (patch.gitBranch !== undefined) {
    const gitBranch = patch.gitBranch.trim()
    if (gitBranch) next.gitBranch = gitBranch
    else delete next.gitBranch
  }
  if (patch.githubRepo !== undefined) {
    const githubRepo = patch.githubRepo.trim()
    if (githubRepo) next.githubRepo = githubRepo
    else delete next.githubRepo
  }
  if (patch.workspacesEnabled !== undefined) {
    if (patch.workspacesEnabled) next.workspacesEnabled = true
    else delete next.workspacesEnabled
  }
  if (patch.command !== undefined) {
    const command = patch.command.trim()
    if (command) next.command = command
    else delete next.command
  }
  if (patch.cliOverride !== undefined) {
    const cli = patch.cliOverride.trim()
    if (cli) next.cliOverride = cli
    else delete next.cliOverride
  }
  if (patch.profileOverride !== undefined) {
    const profile = patch.profileOverride.trim()
    if (profile) next.profileOverride = profile
    else delete next.profileOverride
  }
  if (patch.inferenceList !== undefined) {
    const seats = serializeInferenceList(patch.inferenceList)
    if (seats.length) next.inferenceList = seats
    else delete next.inferenceList
  }
  if (patch.skills !== undefined) {
    const skills = [...new Set(patch.skills.map((name) => name.trim()).filter(Boolean))]
    if (skills.length) next.skills = skills
    else delete next.skills
  }
  if (patch.remote !== undefined) {
    const remote = patch.remote
    const host = String(remote?.host || '').trim()
    const port = Number(remote?.port)
    if (host && Number.isInteger(port) && port > 0) {
      next.remote = {
        host,
        port,
        ...(remote?.username ? { username: remote.username } : {}),
        ...(remote?.password_env ? { password_env: remote.password_env } : {}),
        ...(remote?.box ? { box: remote.box } : {}),
      }
    } else {
      delete next.remote
    }
  }

  if (Object.keys(next).length === 0) delete map[agentId]
  else map[agentId] = next
  writeMap(map)
  emitChange(agentId)
  return next
}

/** REQ-69 ordered inference seats for this agent. Empty = Settings default. */
export function loadInferenceList(agentId: string): InferenceSeat[] {
  if (!agentId) return []
  const edit = loadAgentEdit(agentId)
  const fromList = normalizeInferenceList(edit.inferenceList)
  if (fromList.length) return fromList
  // One-item fallback from the older single override fields.
  if (edit.cliOverride?.trim()) {
    return [{ id: edit.cliOverride.trim(), kind: 'cli', label: edit.cliOverride.trim() }]
  }
  if (edit.profileOverride?.trim()) {
    return [{ id: edit.profileOverride.trim(), kind: 'llm', label: edit.profileOverride.trim() }]
  }
  if (edit.llmOverride?.trim()) {
    return [{ id: edit.llmOverride.trim(), kind: 'llm', label: edit.llmOverride.trim() }]
  }
  return []
}

export function saveInferenceList(agentId: string, seats: InferenceSeat[]): InferenceSeat[] {
  const next = normalizeInferenceList(seats)
  saveAgentEdit(agentId, { inferenceList: serializeInferenceList(next) })
  return next
}

/** Catalog blueprint this agent seat runs. Defaults to the agent id. */
export function assignedBlueprintId(agentId: string): string {
  const assigned = loadAgentEdit(agentId).blueprintId?.trim()
  return assigned || agentId
}

/** Display name: editor override, then catalog name, then id. */
export function editedAgentLabel(agent: { id: string; name?: string | null }): string {
  const override = loadAgentEdit(agent.id).name?.trim()
  if (override) return override
  return agent.name || agent.id
}
