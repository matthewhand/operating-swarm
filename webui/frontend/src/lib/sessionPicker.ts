/**
 * Session list for the #394 / #398 search-style picker.
 *
 * Pre-filtered to one team, remote, or (later) scale-out agent. Running and
 * finished rows. Empty copy is “no sessions yet”.
 */

import { parseStartedAt, type StackFace } from './avatarStack'
import type { RemoteAgent, RemoteEntry } from './remotesCatalog'
import type { TeamRoster } from './teamRosters'

export type SessionStatus = 'running' | 'finished'
export type SessionGroupKind = 'team' | 'remote' | 'agent'

export interface MemberSession {
  id: string
  groupId: string
  groupKind: SessionGroupKind
  memberId: string
  title: string
  snippet: string
  status: SessionStatus
  startedAt: number
  href: string
  role?: string
  avatarSrc?: string | null
}

export function facesFromSessions(sessions: MemberSession[]): StackFace[] {
  return sessions.map((session) => ({
    id: session.memberId || session.id,
    name: session.title,
    startedAt: session.startedAt,
    role: session.role,
    working: session.status === 'running',
    avatarSrc: session.avatarSrc,
  }))
}

export function filterSessions(sessions: MemberSession[], query: string): MemberSession[] {
  const q = query.trim().toLowerCase()
  if (!q) return sessions
  return sessions.filter((session) => {
    return (
      session.title.toLowerCase().includes(q) ||
      session.snippet.toLowerCase().includes(q) ||
      session.memberId.toLowerCase().includes(q)
    )
  })
}

function memberName(member: { id: string; name?: string }): string {
  return (member.name && member.name.trim()) || member.id
}

function memberStatus(member: {
  working?: boolean
  status?: string
}): SessionStatus {
  if (member.status === 'running' || member.working) return 'running'
  return 'finished'
}

export function sessionsForTeam(team: TeamRoster): MemberSession[] {
  return team.members.map((member, index) => {
    const memberId = member.team_id && member.kind === 'team' ? member.team_id : member.id
    const startedAt = parseStartedAt(member.started_at ?? member.startedAt, index)
    const href =
      member.kind === 'team'
        ? `/chat?team=${encodeURIComponent(member.team_id || member.id)}`
        : `/chat?team=${encodeURIComponent(team.id)}&session=${encodeURIComponent(member.id)}`
    return {
      id: `${team.id}:${member.id}`,
      groupId: team.id,
      groupKind: 'team',
      memberId,
      title: memberName(member),
      snippet: member.snippet || [member.kind, member.role].filter(Boolean).join(' · '),
      status: memberStatus(member),
      startedAt,
      href,
      role: member.role,
      avatarSrc: member.avatarSrc || member.avatar_path || member.avatar || member.src || null,
    }
  })
}

export function sessionsForRemote(remote: RemoteEntry): MemberSession[] {
  const agents: RemoteAgent[] = remote.agents.length
    ? remote.agents
    : [{ id: remote.id, name: remote.title, startedAt: 0 }]
  return agents.map((agent, index) => {
    const startedAt = parseStartedAt(agent.startedAt ?? agent.started_at, index)
    return {
      id: `${remote.id}:${agent.id}`,
      groupId: remote.id,
      groupKind: 'remote',
      memberId: agent.id,
      title: agent.name || agent.id,
      snippet: agent.snippet || [agent.role, agent.status].filter(Boolean).join(' · '),
      status: memberStatus(agent),
      startedAt,
      href: `/chat?remote=${encodeURIComponent(remote.id)}&session=${encodeURIComponent(agent.id)}`,
      role: agent.role,
      avatarSrc: (agent as any).avatarSrc || (agent as any).avatar_path || (agent as any).avatar || (agent as any).src || null,
    }
  })
}

export function stackFacesForTeam(team: TeamRoster): StackFace[] {
  return facesFromSessions(sessionsForTeam(team))
}

export function stackFacesForRemote(remote: RemoteEntry): StackFace[] {
  return facesFromSessions(sessionsForRemote(remote))
}

/**
 * REQ-130 / REQ-846: Default talk-to session for a team.
 * Prefers configured Chief of Staff (cos / chief_of_staff), falls back to first member.
 */
export function defaultSessionForTeam(team: TeamRoster): MemberSession | null {
  const sessions = sessionsForTeam(team)
  if (sessions.length === 0) return null
  const cos = sessions.find(
    (s) =>
      s.memberId === 'cos' ||
      s.role === 'chief_of_staff' ||
      s.role === 'cos' ||
      /chief.?of.?staff/i.test(s.role || '') ||
      /cos/i.test(s.title),
  )
  return cos || sessions[0] || null
}

/**
 * "Select Agent" is only useful when there is more than one listed bot
 * (or team member) to choose. Zero or one: omit the control. A single
 * bot is already implicit; an empty remote uses the existing Add/bind path.
 */
export function shouldShowSelectAgent(
  sessions: readonly MemberSession[] | null | undefined,
): boolean {
  return Boolean(sessions && sessions.length > 1)
}

/**
 * REQ-130: Default talk-to session for a remote.
 * Prefers configured Chief of Staff, falls back to first member.
 */
export function defaultSessionForRemote(remote: RemoteEntry): MemberSession | null {
  const sessions = sessionsForRemote(remote)
  if (sessions.length === 0) return null
  const cos = sessions.find(
    (s) =>
      s.memberId === 'cos' ||
      s.role === 'chief_of_staff' ||
      s.role === 'cos' ||
      /chief.?of.?staff/i.test(s.role || '') ||
      /cos/i.test(s.title),
  )
  return cos || sessions[0] || null
}

