/**
 * Agent skills editor + pack picker helpers (#1393).
 *
 * Description is the when-to-use hint. Export requires gettingStarted.skill
 * to name a selected (packed) skill — same constraint as the #1392 backend.
 */

import type { AgentGettingStarted, AgentPack, AgentSkillRecord } from './api'

export const WHEN_TO_USE_LABEL = 'When to use'

export function skillWhenToUse(skill: Pick<AgentSkillRecord, 'description'> | null | undefined): string {
  return String(skill?.description || '').trim()
}

export function normalizeSkillName(value: string | null | undefined): string {
  return String(value || '')
    .trim()
    .toLowerCase()
}

export function uniqueSkillNames(names: Iterable<string>): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of names) {
    const name = normalizeSkillName(raw)
    if (!name || seen.has(name)) continue
    seen.add(name)
    out.push(name)
  }
  return out
}

export function gettingStartedName(
  raw: AgentGettingStarted | string | null | undefined,
): string {
  if (!raw) return ''
  if (typeof raw === 'string') return normalizeSkillName(raw)
  return normalizeSkillName(raw.skill)
}

/** True when gettingStarted names one of the selected skills. */
export function gettingStartedInSelection(
  selected: Iterable<string>,
  gettingStarted: AgentGettingStarted | string | null | undefined,
): boolean {
  const name = gettingStartedName(gettingStarted)
  if (!name) return false
  return uniqueSkillNames(selected).includes(name)
}

export function canExportAgentPack(
  selected: Iterable<string>,
  gettingStarted: AgentGettingStarted | string | null | undefined,
): boolean {
  const names = uniqueSkillNames(selected)
  return names.length > 0 && gettingStartedInSelection(names, gettingStarted)
}

export function exportBlockedReason(
  selected: Iterable<string>,
  gettingStarted: AgentGettingStarted | string | null | undefined,
): string | null {
  const names = uniqueSkillNames(selected)
  if (names.length === 0) return 'Select at least one skill to export.'
  if (!gettingStartedName(gettingStarted)) {
    return 'Pick a getting-started skill from the selected skills.'
  }
  if (!gettingStartedInSelection(names, gettingStarted)) {
    return 'gettingStarted must name a selected skill.'
  }
  return null
}

export function pickerOptionsForSelection(selected: Iterable<string>): string[] {
  return uniqueSkillNames(selected)
}

export function parsePackJson(raw: string): unknown {
  const text = String(raw || '').trim()
  if (!text) throw new Error('Paste or drop a pack JSON document.')
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    throw new Error('Invalid JSON: pack document must be valid JSON.')
  }
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    const body = parsed as Record<string, unknown>
    if (body.pack && typeof body.pack === 'object') return body.pack
  }
  return parsed
}

export function gettingStartedFlowFromList(payload: {
  object?: string
  skills?: AgentSkillRecord[]
  gettingStarted?: AgentGettingStarted | null
  first_run_pending?: boolean
} | null | undefined): {
  skill: string
  whenToUse: string
  chip: string
} | null {
  if (!payload || payload.object !== 'agent_skill_list') return null
  if (!payload.first_run_pending) return null
  const name = gettingStartedName(payload.gettingStarted)
  if (!name) return null
  const skill = (payload.skills || []).find((row) => row.name === name)
  const whenToUse = skillWhenToUse(skill) || `Start with ${name}`
  return {
    skill: name,
    whenToUse,
    chip: whenToUse,
  }
}

export function downloadAgentPack(pack: AgentPack, filename?: string): void {
  const blob = new Blob([`${JSON.stringify(pack, null, 2)}\n`], {
    type: 'application/json',
  })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  const started = gettingStartedName(pack.gettingStarted) || 'pack'
  anchor.href = url
  anchor.download = filename || `agent-pack-${started}.json`
  anchor.rel = 'noopener'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
