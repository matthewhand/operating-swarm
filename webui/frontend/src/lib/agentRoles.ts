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

/* ------------------------------------------------------------------ *
 * #1706 D.14/D.15/D.16 — which seats may carry a role at all.
 *
 * This is the FE's single seat-capability decision point, and it is the
 * same rule the backend enforces in `validate_role_for_kind`
 * (`src/swarm/core/roles/registry.py`). Keeping the two in step is the whole
 * point: `roleAllowedOnSeatKind` backs both the picker's option filter and the
 * write guard, and `roleEditableForSeat` decides whether the field exists at
 * all — so neither can advertise a role the API would refuse to store.
 *
 * Two seat shapes own no role of their own:
 *
 *   `team` — a roster. Its members have roles; the roster does not.
 *   `chat` — a dedicated chat session. It hangs off an agent seat, and the
 *            role belongs to that seat, not to the conversation.
 *
 * `chat` is identified by the rail's own `chat:<agentId>:<sessionId>` row id,
 * reusing `RAIL_CHAT_ROW_PREFIX` from `lib/railChatRows` rather than
 * re-declaring it — the constraints forbid a second identity system, and that
 * prefix is already the product's name for this thing.
 * ------------------------------------------------------------------ */

import { RAIL_CHAT_ROW_PREFIX } from './railChatRows'

/** Seat shapes that cannot be assigned a role (#1706 §D). */
export const ROLE_INCAPABLE_SEAT_KINDS = ['team', 'chat'] as const
export type RoleIncapableSeatKind = (typeof ROLE_INCAPABLE_SEAT_KINDS)[number]

/**
 * Why the role field is unavailable, in the operator's words.
 *
 * This is a **programmatic** reason, not a missing control: the editor
 * renders it and points the field's `aria-describedby` at it, so a
 * screen-reader user is told the field is unavailable rather than being
 * handed a form with a silent hole in it.
 */
export const ROLE_FIELD_UNAVAILABLE_REASON =
  'Teams and chat sessions cannot be assigned a role. A role belongs to an ' +
  'individual agent seat; open the team or chat’s owning agent to set one.'

/** Strip taxonomy prefixes so the seat id can classify. */
function peeledSeatId(raw: string | null | undefined): string {
  let text = String(raw ?? '').trim().toLowerCase()
  while (text.startsWith('blueprint:')) text = text.slice('blueprint:'.length)
  return text
}

/**
 * Is this seat id a dedicated chat session?
 *
 * Pure on the id, so both the editor and any future caller classify the same
 * way without a store read.
 */
export function isChatSeatId(agentId: string | null | undefined): boolean {
  return peeledSeatId(agentId).startsWith(RAIL_CHAT_ROW_PREFIX)
}

/**
 * The seat kind *for role purposes* that this editor session addresses.
 *
 * A classifier, not the rule: it answers "what kind of thing is this?" so
 * {@link roleEditableForSeat} can be the only place a decision is made.
 *
 * The source-style prefixes are read here rather than defaulting to `api`,
 * because a wrong default is not inert: it would put a `remote`/`cli` seat in
 * the api bucket, where {@link roleAllowedOnSeatKind} would happily offer the
 * `support` role the backend refuses (#853). When nothing in the id says
 * otherwise, `kindHint` — the editor's own computed kind — decides, and `api`
 * is the last resort, matching the backend classifier's fallthrough.
 */
export function roleSeatKindFor(
  agentId: string | null | undefined,
  kindHint?: string | null,
): string {
  const peeled = peeledSeatId(agentId)
  if (peeled.startsWith(RAIL_CHAT_ROW_PREFIX)) return 'chat'
  if (peeled.startsWith('team:')) return 'team'
  if (peeled.startsWith('cli:') || peeled === 'cli_agent') return 'cli'
  if (
    peeled.startsWith('remote:') ||
    peeled.startsWith('placeholder:remote:') ||
    peeled.startsWith('herdr:') ||
    peeled === 'remote_harness'
  ) {
    return 'remote'
  }
  // A hint may refine an otherwise-unknown id, but never re-label a team or a
  // chat: those identities are carried by the id itself.
  return String(kindHint || '').trim().toLowerCase() || 'api'
}

/** What the editor must do with the role field for one seat. */
export interface RoleFieldAvailability {
  /** False ⇒ hide/disable the role field and render {@link reason}. */
  editable: boolean
  /** The seat kind the decision was made from, for the reason's wording. */
  seatKind: string
  /** Always populated (empty when editable) so `aria-describedby` is safe. */
  reason: string
}

/**
 * The one place the editor asks "may this seat carry a role?".
 *
 * Mirrors the backend's `validate_role_for_kind`: `default` is always allowed
 * (it is the absence of a role), and `team` / `chat` allow no role at all.
 */
export function roleEditableForSeat(
  agentId: string | null | undefined,
  kindHint?: string | null,
): RoleFieldAvailability {
  const seatKind = roleSeatKindFor(agentId, kindHint)
  const incapable = (ROLE_INCAPABLE_SEAT_KINDS as readonly string[]).includes(seatKind)
  return {
    editable: !incapable,
    seatKind,
    reason: incapable ? ROLE_FIELD_UNAVAILABLE_REASON : '',
  }
}

/**
 * The backend's #853 rule, mirrored: the `support` role leans on structured
 * function-calling hooks that only API seats have.
 *
 * Exists so the picker's option filter and its write guard read ONE function
 * instead of each spelling `role === 'support' && kind !== 'api'`. The backend
 * half of the same rule is `validate_role_for_kind`, which also covers the
 * #1706 team/chat case — so the two halves of the rule have exactly one FE
 * expression and one BE expression, both of which callers reuse.
 */
export const SUPPORT_ROLE_SEAT_KINDS = ['api', 'blueprint'] as const

export function roleAllowedOnSeatKind(
  role: string | null | undefined,
  seatKind: string | null | undefined,
): boolean {
  const normalized = normalizeAgentRole(role)
  // `default` is the absence of a role, so it is valid everywhere — including
  // on a team or chat, which is why a *clearing* write is never rejected.
  if (normalized === 'default') return true
  const seat = String(seatKind || '').trim().toLowerCase()
  if ((ROLE_INCAPABLE_SEAT_KINDS as readonly string[]).includes(seat)) return false
  if (normalized !== 'support') return true
  return (SUPPORT_ROLE_SEAT_KINDS as readonly string[]).includes(seat)
}


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
