/**
 * Navbar routing path (REQ-200 / #676).
 *
 * One control joins agent → model → effort. Effort is parsed from discovered
 * model ids (suffix low/medium/high) — never invented, never "You"/"Default".
 */

export const EFFORT_TOKENS = ['low', 'medium', 'high'] as const
export type EffortToken = (typeof EFFORT_TOKENS)[number]

/** Mystery labels removed by REQ-186 — never show these as routing pills. */
export const HIDDEN_ROUTING_LABELS = new Set(['you', 'default'])

export const ROUTING_PATH_SEP = ' / '

/** '#755': team seats route through the same picker — the member is the agent. */
export type RoutingSeatKind = 'cli' | 'remote' | 'api' | 'blueprint' | 'team'

export type RoutingDimension = 'agent' | 'model' | 'effort'

export interface ModelFamily {
  base: string
  efforts: EffortToken[]
  ids: string[]
}

export interface RoutingPath {
  agent: string
  model: string
  modelBase: string
  effort: EffortToken | null
}

export function isEffortToken(value: string): value is EffortToken {
  return (EFFORT_TOKENS as readonly string[]).includes(value.trim().toLowerCase())
}

export function isHiddenRoutingLabel(label: string): boolean {
  return HIDDEN_ROUTING_LABELS.has(label.trim().toLowerCase())
}

export function displayableModels(models: Iterable<string>): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const raw of models) {
    const id = raw.trim()
    if (!id || isHiddenRoutingLabel(id) || seen.has(id)) continue
    seen.add(id)
    out.push(id)
  }
  return out
}

export function parseModelEffort(modelId: string): {
  base: string
  effort: EffortToken | null
} {
  const trimmed = modelId.trim()
  if (!trimmed) return { base: '', effort: null }
  const parts = trimmed.split('-')
  if (parts.length < 2) return { base: trimmed, effort: null }
  const last = parts[parts.length - 1].toLowerCase()
  if (isEffortToken(last)) {
    return { base: parts.slice(0, -1).join('-'), effort: last }
  }
  return { base: trimmed, effort: null }
}

export function composeModelId(base: string, effort: string | null | undefined): string {
  const trimmed = base.trim()
  if (!trimmed) return ''
  if (!effort || !isEffortToken(effort)) return trimmed
  return `${trimmed}-${effort}`
}

export function groupModelsByFamily(models: Iterable<string>): ModelFamily[] {
  const map = new Map<string, ModelFamily>()
  for (const id of displayableModels(models)) {
    const { base, effort } = parseModelEffort(id)
    const family = map.get(base) ?? { base, efforts: [], ids: [] }
    family.ids.push(id)
    if (effort && !family.efforts.includes(effort)) family.efforts.push(effort)
    map.set(base, family)
  }
  for (const family of map.values()) {
    family.efforts.sort((a, b) => EFFORT_TOKENS.indexOf(a) - EFFORT_TOKENS.indexOf(b))
  }
  return [...map.values()]
}

export function familyHasEffort(family: ModelFamily): boolean {
  return family.efforts.length > 0
}

export function defaultEffortForFamily(
  family: ModelFamily,
  preferred?: string | null,
): EffortToken | null {
  if (family.efforts.length === 0) return null
  const want = (preferred || '').trim().toLowerCase()
  if (isEffortToken(want) && family.efforts.includes(want)) return want
  if (family.efforts.includes('medium')) return 'medium'
  return family.efforts[0]
}

export function resolveComposedModel(
  models: Iterable<string>,
  desiredBase?: string | null,
  preferredEffort?: string | null,
): RoutingPath | null {
  const families = groupModelsByFamily(models)
  if (families.length === 0) return null
  const wanted = (desiredBase || '').trim()
  const family = (wanted && families.find((row) => row.base === wanted)) || families[0]
  const effort = defaultEffortForFamily(family, preferredEffort)
  const composed = composeModelId(family.base, effort)
  const existing = family.ids.find((id) => id === composed) || family.ids[0]
  const parsed = parseModelEffort(existing)
  return {
    agent: '',
    model: existing,
    modelBase: parsed.base,
    effort: parsed.effort,
  }
}

export function joinRoutingPath(parts: Array<string | null | undefined>): string {
  return parts
    .map((part) => (part || '').trim())
    .filter((part) => part && !isHiddenRoutingLabel(part))
    .join(ROUTING_PATH_SEP)
}

export function splitRoutingPath(path: string): string[] {
  return path
    .split('/')
    .map((part) => part.trim())
    .filter(Boolean)
}

export function routingPathFromSelection(opts: {
  agent: string
  model?: string | null
  effort?: string | null
}): RoutingPath {
  const parsed = parseModelEffort(opts.model || '')
  const effortRaw = (opts.effort || parsed.effort || '').trim().toLowerCase()
  const effort = isEffortToken(effortRaw) ? effortRaw : parsed.effort
  return {
    agent: (opts.agent || '').trim(),
    model: (opts.model || '').trim(),
    modelBase: parsed.base,
    effort,
  }
}

export function routingFaceParts(path: RoutingPath, models: Iterable<string>): string[] {
  const parts = [path.agent]
  const families = groupModelsByFamily(models)
  if (families.length === 0) return parts.filter(Boolean)
  if (path.modelBase && !isHiddenRoutingLabel(path.modelBase)) parts.push(path.modelBase)
  const family = families.find((row) => row.base === path.modelBase)
  if (family && familyHasEffort(family) && path.effort) parts.push(path.effort)
  return parts.filter(Boolean)
}
