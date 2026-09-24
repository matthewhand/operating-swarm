import type { AgentRole, Blueprint, BlueprintWorkflow } from './api'
import { loadAgentEdit, saveAgentEdit, type AgentEdit } from './agentEdits'
import { SUPPORT_AGENT_ID, SYNTHETIC_SUPPORT, isSupportAgent } from './supportAgent'
import { findCustomRole } from './customRoles'

/** Example roles that demonstrate blueprint design (REQ-25). */
export const EXAMPLE_ROLES = ['support', 'gate', 'skeptic'] as const
export type ExampleRole = (typeof EXAMPLE_ROLES)[number]

export const GATE_AGENT_ID = 'gate'
export const BELAY_AGENT_ID = 'belay'
export const SKEPTIC_AGENT_ID = 'skeptic'
export const COS_AGENT_ID = 'cos'

const ROLE_ALIASES: Record<string, AgentRole> = {
  default: 'default',
  worker: 'default',
  agent: 'default',
  coordinator: 'default',
  admin: 'admin',
  administrator: 'admin',
  sysadmin: 'admin',
  support: 'support',
  helper: 'support',
  gate: 'gate',
  belay: 'gate',
  belayer: 'gate',
  safety: 'gate',
  tool_gate: 'gate',
  'tool-gate': 'gate',
  toolgate: 'gate',
  skeptic: 'skeptic',
  reviewer: 'skeptic',
  advisor: 'advisor',
  adviser: 'advisor',
  mentor: 'advisor',
  chief_of_staff: 'chief_of_staff',
  'chief-of-staff': 'chief_of_staff',
  chiefofstaff: 'chief_of_staff',
  cos: 'chief_of_staff',
  chief: 'chief_of_staff',
  engineer: 'engineer',
  eng: 'engineer',
  none: 'default',
  suggestions: 'suggestions',
  suggestion: 'suggestions',
  suggest: 'suggestions',
}

export const SYNTHETIC_GATE: Blueprint = {
  id: GATE_AGENT_ID,
  object: 'blueprint',
  name: 'Safety',
  description: 'YES/NO classifier for pending tool calls.',
  abbreviation: null,
  required_mcp_servers: [],
  tags: [],
  installed: true,
  compiled: true,
  role: 'gate',
  rail: true,
}

export const SYNTHETIC_SKEPTIC: Blueprint = {
  id: SKEPTIC_AGENT_ID,
  object: 'blueprint',
  name: 'Skeptic',
  description: 'Bounded retry reviewer after a run.',
  abbreviation: null,
  required_mcp_servers: [],
  tags: [],
  installed: true,
  compiled: true,
  role: 'skeptic',
  rail: true,
}

const SYNTHETICS: Record<ExampleRole, Blueprint> = {
  support: { ...SYNTHETIC_SUPPORT, role: 'support' },
  gate: SYNTHETIC_GATE,
  skeptic: SYNTHETIC_SKEPTIC,
}

/** Live runtime modules to link when present (do not rewrite them here). */
export const ROLE_RUNTIME_MODULES: Record<ExampleRole, { label: string; path: string }[]> = {
  support: [{ label: 'blueprint_support.py', path: 'src/swarm/blueprints/support/blueprint_support.py' }],
  gate: [{ label: 'tool_gate', path: 'src/swarm/core/tool_gate.py' }],
  skeptic: [{ label: 'skeptic', path: 'src/swarm/core/skeptic.py' }],
}

export const ROLE_FALLBACK_SOURCE: Record<ExampleRole, string> = {
  support: `# Blueprint recipe — Support (Socratic)
# Role = badge + wiring on a Team member. This file is the Python/API recipe.
# Runtime modules (when present): src/swarm/blueprints/support/blueprint_support.py

SUPPORT_INSTRUCTIONS = (
    "You are Support. Talk about the other agents and how this team is wired. "
    "Stay Socratic: ask one clarifying question at a time, offer a short "
    "multiple-choice when the user is stuck, and never take over the work."
)

def ask_user(question: str, choices: list[str] | None = None) -> str:
    """Elicit the operator. MCQ when choices are given; otherwise free text."""
    if choices:
        return f"MCQ: {question} | " + " / ".join(choices)
    return f"ASK: {question}"
`,
  gate: `# Blueprint recipe — Safety (YES/NO via submit_gate_verdict)
# Role = badge + wiring on a Team member. This file is the Python/API recipe.
# Runtime module (when present): src/swarm/core/safety.py
# Unwired Safety is fail-open: every tool call is approved and the user is never asked.

GATE_INSTRUCTIONS = (
    "You are Safety. Classify the pending tool call as concerning or not. "
    "When done, you MUST call submit_gate_verdict with verdict=\\"yes\\" if the "
    "call is dangerous or verdict=\\"no\\" if it is not. Optional reason. "
    "Example: submit_gate_verdict(verdict=\\"yes\\", reason=\\"destructive rm -rf\\"). "
    "Prose alone is not a verdict."
)

def submit_gate_verdict(verdict: str, reason: str = "") -> str:
    """Finish the gate determination (yes = dangerous → elicit; no = safe)."""
    raise NotImplementedError("live classifier is swarm.core.classifier_verdict")
`,
  skeptic: `# Blueprint recipe — Skeptic (bounded retry via submit_skeptic_verdict)
# Role = badge + wiring on a Team member. This file is the Python/API recipe.
# Runtime module (when present): src/swarm/core/skeptic.py
# On pass stop. On fail, hand findings back (max 2 retries). Do not nag.

SKEPTIC_MAX_RETRIES = 2
SKEPTIC_INSTRUCTIONS = (
    "You are a skeptic. You see the original prompt plus the agent's output. "
    "When done, you MUST call submit_skeptic_verdict with verdict=\\"pass\\" "
    "if accomplished or verdict=\\"fail\\" if not. Optional reason. "
    "Example: submit_skeptic_verdict(verdict=\\"fail\\", reason=\\"summary.md missing\\"). "
    "Prose alone is not a verdict. Do not nag."
)

def submit_skeptic_verdict(verdict: str, reason: str = "") -> str:
    """Finish the skeptic determination (pass/fail)."""
    raise NotImplementedError("live retry loop is swarm.core.classifier_verdict")
`,
}

export function normalizeAgentRole(value: unknown): AgentRole {
  if (value == null) return 'default'
  const key = String(value).trim().toLowerCase().replace(/\s+/g, '_').replace(/-/g, '_')
  if (!key) return 'default'
  if (ROLE_ALIASES[key]) return ROLE_ALIASES[key]
  const custom = findCustomRole(key)
  if (custom) return custom.name
  return 'default'
}

export function agentRole(agent: {
  id?: string | null
  name?: string | null
  role?: unknown
}): AgentRole {
  const edited = agent.id ? loadAgentEdit(agent.id).role : undefined
  if (edited) return normalizeAgentRole(edited)
  const explicit = normalizeAgentRole(agent.role)
  if (explicit !== 'default') return explicit
  if (isSupportAgent({ id: agent.id || '', name: agent.name })) return 'support'
  const id = (agent.id || '').trim().toLowerCase()
  const name = (agent.name || '').trim().toLowerCase()
  if (
    id === GATE_AGENT_ID ||
    name === 'gate' ||
    name === 'tool gate' ||
    name === 'safety'
  ) {
    return 'gate'
  }
  if (id === SKEPTIC_AGENT_ID || name === 'skeptic') return 'skeptic'
  if (
    id === COS_AGENT_ID
    || id === 'chief'
    || id === 'chief-of-staff'
    || id === 'chief_of_staff'
    || name === 'cos'
    || name === 'chief of staff'
  ) {
    return 'chief_of_staff'
  }
  if (id === 'suggestions' || id === 'suggestion' || name === 'suggestions') {
    return 'suggestions'
  }
  return normalizeAgentRole(id) === 'default' ? 'default' : normalizeAgentRole(id)
}

export const ROLE_CHIEF_OF_STAFF = 'chief_of_staff'
export const ROLE_ADVISOR = 'advisor'

export const ROLE_BADGE_LABELS: Record<AgentRole, string> = {
  default: '',
  admin: 'Admin',
  support: 'Support',
  gate: 'Belay',
  belay: 'Belay',
  skeptic: 'Skeptic',
  advisor: 'Advisor',
  chief_of_staff: 'CoS',
  engineer: 'Engineer',
  suggestions: 'Suggest',
}

export function isBelay(role: unknown): boolean {
  const norm = normalizeAgentRole(role)
  return norm === 'gate' || norm === 'belay'
}

export const isGate = isBelay


export function isAdvisor(role: unknown): boolean {
  return normalizeAgentRole(role) === ROLE_ADVISOR
}

export function isChiefOfStaff(role: unknown): boolean {
  return normalizeAgentRole(role) === ROLE_CHIEF_OF_STAFF
}

export function roleBadgeLabel(role: unknown): string {
  const norm = normalizeAgentRole(role)
  if (ROLE_BADGE_LABELS[norm]) return ROLE_BADGE_LABELS[norm]
  const custom = findCustomRole(norm)
  if (custom) return custom.label || custom.name.charAt(0).toUpperCase() + custom.name.slice(1)
  return ''
}

export function roleFromAgent(agent: {
  role?: unknown
  id?: string | null
  name?: string | null
}): AgentRole {
  return agentRole(agent)
}

export function isExampleRole(role: string): role is ExampleRole {
  return (EXAMPLE_ROLES as readonly string[]).includes(role)
}

/** True when the seat has a first-class role (not `default` / `none`). */
export function agentHasRole(agent: {
  id?: string | null
  name?: string | null
  role?: string | null
}): boolean {
  return agentRole(agent) !== 'default'
}

/** Hover-edit is for example roles (or a default row that already has a role blueprint). */
export function showsBlueprintEdit(agent: {
  id?: string | null
  name?: string | null
  role?: string | null
}): boolean {
  return isExampleRole(agentRole(agent))
}

export function roleCssClass(role: AgentRole | string): string {
  const norm = normalizeAgentRole(role)
  const custom = findCustomRole(norm)
  if (custom && custom.css_class) return custom.css_class
  return `os-agent-role-${norm}`
}

export function isExampleRoleAgent(agent: {
  id?: string | null
  name?: string | null
  role?: string | null
}): boolean {
  return showsBlueprintEdit(agent)
}

function hasRole(agents: Blueprint[], role: ExampleRole): boolean {
  return agents.some((agent) => agentRole(agent) === role)
}

/** Inject Support / Safety / Skeptic seats so the three example roles are visible. */
export function ensureExampleRoleAgents(agents: Blueprint[]): Blueprint[] {
  const next = [...agents]
  if (!next.some(isSupportAgent) && !hasRole(next, 'support')) {
    next.unshift(SYNTHETICS.support)
  }
  if (!hasRole(next, 'gate')) next.push(SYNTHETICS.gate)
  if (!hasRole(next, 'skeptic')) next.push(SYNTHETICS.skeptic)
  return next
}

export function sortExampleRolesFirst(agents: Blueprint[]): Blueprint[] {
  const rank = (agent: Blueprint): number => {
    const role = agentRole(agent)
    if (role === 'support') return 0
    if (role === 'gate') return 1
    if (role === 'skeptic') return 2
    return 3
  }
  return [...agents].sort((a, b) => {
    const ra = rank(a)
    const rb = rank(b)
    if (ra !== rb) return ra - rb
    return (a.name || a.id).localeCompare(b.name || b.id)
  })
}

export function exampleRoleAgents(agents: Blueprint[]): Blueprint[] {
  return sortExampleRolesFirst(ensureExampleRoleAgents(agents))
}

export function fallbackBlueprintSource(blueprintId: string, role: AgentRole): string {
  if (isExampleRole(role)) return ROLE_FALLBACK_SOURCE[role]
  if (role === 'chief_of_staff') {
    return (
      `# Blueprint recipe — Chief of Staff (talk-to-any-team)\n` +
      `COS_INSTRUCTIONS = (\n` +
      `    "You are Chief of Staff. Route the operator to the right team. "\n` +
      `    "Talk to any roster; do not do the specialist work yourself."\n` +
      `)\n`
    )
  }
  if (role === 'suggestions') {
    return (
      `# Blueprint recipe — Suggestions (quick-select chips)\n` +
      `SUGGESTIONS_INSTRUCTIONS = (\n` +
      `    "Return JSON {\\"suggestions\\": [2-5 short strings]} the operator can click."\n` +
      `)\n`
    )
  }
  if (role === 'engineer') {
    return (
      `# Blueprint recipe — Engineer (implementer)\n` +
      `ENGINEER_INSTRUCTIONS = (\n` +
      `    "You are the engineer. Implement the quoted issue after the gate. "\n` +
      `    "Do not start without a quoted Intent/Success and feasibility."\n` +
      `)\n`
    )
  }
  return (
    `# Blueprint ${blueprintId}\n` +
    `# No source is published for this agent yet.\n` +
    `# The editor edits a Blueprint (Python/API recipe), not a Team roster.\n`
  )
}

export function runtimeModulesFor(role: AgentRole): { label: string; path: string }[] {
  return isExampleRole(role) ? ROLE_RUNTIME_MODULES[role] : []
}

export function normalizeWorkflow(value: unknown): BlueprintWorkflow | null {
  if (value == null) return null
  const key = String(value).trim().toLowerCase().replace(/\s+/g, '_')
  if (key === 'handoff' || key === 'handoffs') return 'handoff'
  if (key === 'as_tool' || key === 'as-tool' || key === 'astool') return 'as_tool'
  return null
}

/** Leftover webui/django-chat recipes. Pickers must not offer a webui kind. */
export function isWebuiBlueprint(bp: {
  id?: string | null
  kind?: string | null
  webui?: boolean | null
  urls_module?: string | null
  url_prefix?: string | null
}): boolean {
  if (bp.webui === true) return true
  const id = (bp.id || '').trim().toLowerCase().replace(/-/g, '_')
  if (id === 'django_chat') return true
  const kind = (bp.kind || '').trim().toLowerCase().replace(/-/g, '_')
  if (kind === 'webui' || kind === 'django_chat' || kind === 'webpage') return true
  if (bp.urls_module || bp.url_prefix) return true
  return false
}

/** Catalog recipes a picker may assign. Never a webui kind. */
export function assignableBlueprints(items: Blueprint[]): Blueprint[] {
  return items.filter((item) => !isWebuiBlueprint(item))
}

export function catalogPickerLabel(item: {
  id: string
  name?: string | null
  role?: string | null
}): string {
  const name = item.name || item.id
  const badge = roleBadgeLabel(item.role ?? agentRole(item))
  if (!badge) return name
  if (name.toLowerCase() === badge.toLowerCase()) return name
  return `${name} · ${badge}`
}

/**
 * Assign a catalog blueprint to a seat (REQ-75).
 *
 * Re-applies the blueprint default role unless the operator has explicitly
 * overridden the role in the agent editor. Workflow hint is metadata only.
 */
export function applyBlueprintAssignment(
  agentId: string,
  blueprint: { id: string; role?: string | null; workflow?: string | null },
): AgentEdit {
  const current = loadAgentEdit(agentId)
  const workflow = normalizeWorkflow(blueprint.workflow)
  const patch: AgentEdit = {
    blueprintId: blueprint.id,
    ...(workflow ? { workflow } : {}),
  }
  if (!current.roleOverridden) {
    patch.role = normalizeAgentRole(blueprint.role)
  }
  return saveAgentEdit(agentId, patch)
}

export { SUPPORT_AGENT_ID }
