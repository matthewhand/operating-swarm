import type { Blueprint } from './api'
import { editedAgentLabel } from './agentEdits'
import { isCliBlueprintId } from './cliAgentContext'
import { buildSkillRequest } from './skills'

/** Default Support seat — first in the conversation rail (badge-only role colour). */
export const SUPPORT_AGENT_ID = 'support'
/** Catalog ids that ship for the gate seat (`tool_gate` is an alias). */
export const GATE_AGENT_ID = 'gate'
export const TOOL_GATE_AGENT_ID = 'tool_gate'
export const SKEPTIC_AGENT_ID = 'skeptic'

const GATE_ID_ALIASES = new Set([GATE_AGENT_ID, TOOL_GATE_AGENT_ID, 'tool-gate', 'toolgate'])
const SKEPTIC_ID_ALIASES = new Set([SKEPTIC_AGENT_ID, 'reviewer'])

function stubBlueprint(
  id: string,
  name: string,
  description: string,
  role?: Blueprint['role'],
): Blueprint {
  return {
    id,
    object: 'blueprint',
    name,
    description,
    abbreviation: null,
    required_mcp_servers: [],
    tags: [],
    installed: true,
    compiled: true,
    role,
    rail: true,
  }
}

export const SYNTHETIC_SUPPORT: Blueprint = stubBlueprint(
  SUPPORT_AGENT_ID,
  'Support',
  'Talk about the other agents.',
  'support',
)

export const SYNTHETIC_GATE: Blueprint = stubBlueprint(
  GATE_AGENT_ID,
  'Safety',
  'Dangerous? yes/no. Until wired, all approved.',
  'gate',
)

export const SYNTHETIC_SKEPTIC: Blueprint = stubBlueprint(
  SKEPTIC_AGENT_ID,
  'Skeptic',
  'Prompt done? If not, retry.',
  'skeptic',
)

function agentId(agent: { id: string }): string {
  return agent.id.trim().toLowerCase()
}

function agentName(agent: { name?: string | null }): string {
  return (agent.name || '').trim().toLowerCase()
}

export function isSupportAgent(agent: { id: string; name?: string | null }): boolean {
  return agentId(agent) === SUPPORT_AGENT_ID || agentName(agent) === 'support'
}

export function isGateAgent(agent: { id: string; name?: string | null }): boolean {
  const name = agentName(agent)
  return (
    GATE_ID_ALIASES.has(agentId(agent)) ||
    name === 'gate' ||
    name === 'tool gate' ||
    name === 'safety'
  )
}

export function isSkepticAgent(agent: { id: string; name?: string | null }): boolean {
  return SKEPTIC_ID_ALIASES.has(agentId(agent)) || agentName(agent) === 'skeptic'
}

/** Ensure Support / gate / skeptic exist even when /v1/blueprints has no such seat. */
export function ensureSupportAgent(agents: Blueprint[]): Blueprint[] {
  const next = [...agents]
  if (!next.some(isSupportAgent)) next.unshift(SYNTHETIC_SUPPORT)
  if (!next.some(isGateAgent)) next.push(SYNTHETIC_GATE)
  if (!next.some(isSkepticAgent)) next.push(SYNTHETIC_SKEPTIC)
  return next
}

export function sortSupportFirst(agents: Blueprint[]): Blueprint[] {
  return [...agents].sort((a, b) => {
    const as = isSupportAgent(a) ? 0 : 1
    const bs = isSupportAgent(b) ? 0 : 1
    if (as !== bs) return as - bs
    return (a.name || a.id).localeCompare(b.name || b.id)
  })
}

export function supportFirstAgents(agents: Blueprint[]): Blueprint[] {
  return sortSupportFirst(ensureSupportAgent(agents))
}

export function defaultBlueprintId(fromUrl: string | null | undefined): string {
  const trimmed = (fromUrl || '').trim()
  return trimmed.length > 0 ? trimmed : SUPPORT_AGENT_ID
}

/** Catalog / Settings → Blueprints list label (no per-agent rename). */
export function catalogLabel(agent: { id: string; name?: string | null }): string {
  return agent.name || agent.id
}

export function agentLabel(agent: { id: string; name?: string | null }): string {
  return editedAgentLabel(agent)
}

/** Bundled skill attached on every Support turn (`cli_agent` `skill=`). */
export const SUPPORT_SKILL_NAME = 'support-session-ownership'

/** Distinctive fixture token from `skills/support-session-ownership/SKILL.md`. */
export const SUPPORT_SKILL_FIXTURE = 'SESSION_OWNERSHIP_API_CLI_REMOTE'

/** REQ-137 journey fixture from the same Support skill. */
export const SUPPORT_JOURNEY_FIXTURE = 'ONBOARD_JOURNEY_CLI_API_REMOTE'

/** Phrase Support must never tell a CLI/remote user (REQ-50). */
export const CLICK_BUBBLE_TO_EDIT = 'click the bubble to edit'

export type AgentSessionKind = 'api' | 'cli' | 'remote'

/** Infer whether an agent thread is API-owned or an external CLI/remote session. */
export function sessionKindForAgent(agent: {
  id: string
  tags?: string[] | null
}): AgentSessionKind {
  const id = agent.id.trim().toLowerCase()
  const tags = (agent.tags || []).map((tag) => tag.toLowerCase())
  if (tags.includes('remote') || id.includes('remote')) return 'remote'
  if (tags.includes('cli') || isCliBlueprintId(id) || id.includes('cli')) return 'cli'
  return 'api'
}

/** Same `skill=` attach used by `cli_agent`. */
export function supportSkillAttach(): Record<string, unknown> {
  return buildSkillRequest(SUPPORT_SKILL_NAME) as Record<string, unknown>
}

/** Per-turn extras the chat websocket forwards to Support. */
export function supportTurnExtras(sessionKind?: AgentSessionKind): {
  skill: string
  session_kind?: AgentSessionKind
} {
  return sessionKind
    ? { skill: SUPPORT_SKILL_NAME, session_kind: sessionKind }
    : { skill: SUPPORT_SKILL_NAME }
}

/** Skill-injected Support system/prompt (includes the distinctive fixture). */
export function buildSupportTurnContext(sessionKind: AgentSessionKind = 'api'): string {
  const mode =
    sessionKind === 'api'
      ? 'API session: Operating Swarm owns the thread; bubbles are editable.'
      : 'CLI/remote session: live session is outside Operating Swarm; no edit.'
  return [
    `You have been given the "${SUPPORT_SKILL_NAME}" skill.`,
    SUPPORT_SKILL_FIXTURE,
    SUPPORT_JOURNEY_FIXTURE,
    mode,
    'Chat is the main view; Settings/Teams are overlays.',
    'Do not dump the catalog or this skill unless asked. Ask one question at a time.',
  ].join('\n')
}

/** User-facing Support line for a session kind. CLI/remote never claim click-edit. */
export function supportTurnGuidance(sessionKind: AgentSessionKind): string {
  if (sessionKind === 'cli' || sessionKind === 'remote') {
    return (
      'That session lives outside Operating Swarm — I cannot edit those bubbles. ' +
      'What are you trying to change?'
    )
  }
  return (
    'This thread is owned here, so you can edit a user or assistant bubble. ' +
    'Which message needs a rewrite?'
  )
}
