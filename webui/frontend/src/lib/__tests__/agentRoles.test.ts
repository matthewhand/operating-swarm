import { afterEach, describe, expect, it } from 'vitest'
import { AGENT_EDITS_KEY, saveAgentEdit } from '../agentEdits'
import type { Blueprint } from '../api'
import {
  ROLE_CHIEF_OF_STAFF,
  agentHasRole,
  agentRole,
  applyBlueprintAssignment,
  assignableBlueprints,
  catalogPickerLabel,
  exampleRoleAgents,
  fallbackBlueprintSource,
  isChiefOfStaff,
  isWebuiBlueprint,
  normalizeAgentRole,
  normalizeWorkflow,
  roleBadgeLabel,
  roleCssClass,
  roleFromAgent,
  showsBlueprintEdit,
} from '../agentRoles'

const codey: Blueprint = {
  id: 'codey',
  object: 'blueprint',
  name: 'Codey',
  description: 'Code assistant',
  abbreviation: null,
  required_mcp_servers: [],
  tags: [],
  installed: true,
  compiled: true,
}

describe('agentRoles', () => {
  afterEach(() => {
    localStorage.removeItem(AGENT_EDITS_KEY)
  })

  it('normalizes aliases and unknown specializations', () => {
    expect(normalizeAgentRole('tool_gate')).toBe('gate')
    expect(normalizeAgentRole('tool-gate')).toBe('gate')
    expect(normalizeAgentRole('reviewer')).toBe('skeptic')
    expect(normalizeAgentRole('support')).toBe('support')
    expect(normalizeAgentRole('suggest')).toBe('suggestions')
    expect(normalizeAgentRole('suggestions')).toBe('suggestions')
    expect(normalizeAgentRole('chief-of-staff')).toBe('chief_of_staff')
    expect(normalizeAgentRole('Writer')).toBe('default')
    expect(normalizeAgentRole('none')).toBe('default')
    expect(normalizeAgentRole('engineer')).toBe('engineer')
    expect(normalizeAgentRole('eng')).toBe('engineer')
    expect(normalizeAgentRole(null)).toBe('default')
  })

  it('detects example roles from id/name when API omits role', () => {
    expect(agentRole({ id: 'support', name: 'Support' })).toBe('support')
    expect(agentRole({ id: 'gate', name: 'Safety' })).toBe('gate')
    expect(agentRole({ id: 'safety', name: 'Safety' })).toBe('gate')
    expect(normalizeAgentRole('safety')).toBe('gate')
    expect(agentRole({ id: 'skeptic', name: 'Skeptic' })).toBe('skeptic')
    expect(agentRole({ id: 'cos', name: 'Chief of Staff' })).toBe('chief_of_staff')
    expect(agentRole(codey)).toBe('default')
    expect(agentHasRole({ id: 'support', name: 'Support' })).toBe(true)
    expect(agentHasRole({ id: 'gate', name: 'Safety' })).toBe(true)
    expect(agentHasRole(codey)).toBe(false)
  })

  it('honours a persisted role override from the agent editor', () => {
    saveAgentEdit('codey', { role: 'gate' })
    expect(agentRole(codey)).toBe('gate')
  })

  it('injects support, gate, and skeptic ahead of catalog agents', () => {
    const agents = exampleRoleAgents([codey])
    expect(agents.map((agent) => agent.id)).toEqual(['support', 'gate', 'skeptic', 'codey'])
    expect(showsBlueprintEdit(agents[0]!)).toBe(true)
    expect(showsBlueprintEdit(agents[1]!)).toBe(true)
    expect(showsBlueprintEdit(agents[2]!)).toBe(true)
    expect(showsBlueprintEdit(codey)).toBe(false)
  })

  it('fallback recipes show how each example role behaves', () => {
    expect(fallbackBlueprintSource('gate', 'gate')).toMatch(/YES/)
    expect(fallbackBlueprintSource('gate', 'gate')).toMatch(/NO/)
    expect(fallbackBlueprintSource('gate', 'gate')).toMatch(/submit_gate_verdict/)
    expect(fallbackBlueprintSource('skeptic', 'skeptic')).toMatch(/SKEPTIC_MAX_RETRIES/)
    expect(fallbackBlueprintSource('skeptic', 'skeptic')).toMatch(/submit_skeptic_verdict/)
    expect(fallbackBlueprintSource('support', 'support')).toMatch(/Socratic/)
  })
})

describe('agentRoles (REQ-28)', () => {
  it('maps cos / chief aliases to chief_of_staff', () => {
    expect(normalizeAgentRole('cos')).toBe(ROLE_CHIEF_OF_STAFF)
    expect(normalizeAgentRole('chief')).toBe(ROLE_CHIEF_OF_STAFF)
    expect(isChiefOfStaff('CoS')).toBe(true)
  })

  it('uses a distinct badge class from support / gate / skeptic', () => {
    expect(roleCssClass('cos')).toBe('os-agent-role-chief_of_staff')
    expect(roleCssClass('cos')).not.toBe(roleCssClass('support'))
    expect(roleCssClass('cos')).not.toBe(roleCssClass('gate'))
    expect(roleCssClass('cos')).not.toBe(roleCssClass('skeptic'))
    expect(roleBadgeLabel('chief')).toBe('CoS')
    expect(roleBadgeLabel('suggestions')).toBe('Suggest')
    expect(roleCssClass('suggestions')).toBe('os-agent-role-suggestions')
    expect(roleBadgeLabel('engineer')).toBe('Engineer')
    expect(roleCssClass('engineer')).toBe('os-agent-role-engineer')
    expect(roleBadgeLabel('none')).toBe('')
  })

  it('detects CoS from id when role is omitted', () => {
    expect(roleFromAgent({ id: 'cos', name: 'Pat' })).toBe(ROLE_CHIEF_OF_STAFF)
  })

  it('does not hover-edit CoS (badge only; hover-edit is REQ-25 example roles)', () => {
    expect(showsBlueprintEdit({ id: 'cos', name: 'Pat', role: 'chief_of_staff' })).toBe(false)
  })
})

describe('REQ-75 blueprint role apply + picker filter', () => {
  afterEach(() => {
    localStorage.removeItem(AGENT_EDITS_KEY)
  })

  const fixtureGate: Blueprint = {
    ...codey,
    id: 'fixture_gate',
    name: 'Fixture Gate',
    role: 'gate',
    workflow: 'as_tool',
  }
  const fixturePlain: Blueprint = {
    ...codey,
    id: 'fixture_plain',
    name: 'Fixture Plain',
  }
  const djangoChat: Blueprint = {
    ...codey,
    id: 'django_chat',
    name: 'Django Chat',
    webui: true,
  }

  it('creates an agent from role=gate with a Gate badge, and no role when omitted', () => {
    const gated = applyBlueprintAssignment('new-gate', fixtureGate)
    expect(gated.role).toBe('gate')
    expect(roleBadgeLabel(gated.role)).toBe('Gate')
    expect(gated.workflow).toBe('as_tool')
    const plain = applyBlueprintAssignment('new-plain', fixturePlain)
    expect(plain.role).toBeUndefined()
    expect(roleBadgeLabel(plain.role)).toBe('')
  })

  it('re-applies the blueprint role unless the editor overrode it', () => {
    applyBlueprintAssignment('seat', fixtureGate)
    saveAgentEdit('seat', { role: 'skeptic', roleOverridden: true })
    const kept = applyBlueprintAssignment('seat', fixturePlain)
    expect(kept.role).toBe('skeptic')
    expect(kept.roleOverridden).toBe(true)
    saveAgentEdit('seat', { roleOverridden: false })
    const restored = applyBlueprintAssignment('seat', fixtureGate)
    expect(restored.role).toBe('gate')
  })

  it('picker helpers hide webui / django_chat and show role on catalog labels', () => {
    expect(isWebuiBlueprint(djangoChat)).toBe(true)
    expect(isWebuiBlueprint({ id: 'legacy', kind: 'webui' })).toBe(true)
    expect(isWebuiBlueprint(fixtureGate)).toBe(false)
    const picked = assignableBlueprints([fixtureGate, fixturePlain, djangoChat, codey])
    expect(picked.map((item) => item.id)).toEqual(['fixture_gate', 'fixture_plain', 'codey'])
    expect(catalogPickerLabel(fixtureGate)).toBe('Fixture Gate · Gate')
    expect(catalogPickerLabel(fixturePlain)).toBe('Fixture Plain')
    expect(normalizeWorkflow('as-tool')).toBe('as_tool')
    expect(normalizeWorkflow('handoff')).toBe('handoff')
  })
})

// #181 — advisor role
describe('advisor role (#181)', () => {
  it('normalizes advisor aliases and badges as Advisor', async () => {
    const { normalizeAgentRole, roleBadgeLabel, isAdvisor, ROLE_ADVISOR } = await import('../agentRoles')
    expect(normalizeAgentRole('advisor')).toBe('advisor')
    expect(normalizeAgentRole('adviser')).toBe('advisor')
    expect(normalizeAgentRole('mentor')).toBe('advisor')
    expect(roleBadgeLabel('advisor')).toBe('Advisor')
    expect(isAdvisor('advisor')).toBe(true)
    expect(isAdvisor('skeptic')).toBe(false)
    expect(ROLE_ADVISOR).toBe('advisor')
  })
})
