/**
 * Provider grouping + search for the API model palette (#281).
 *
 * LiteLLM-style ids (`anthropic/…`, `gpt-…`, `claude-…`) group by provider;
 * named LLM profiles without a provider prefix land in `Profiles`.
 */

export interface ModelSearchOption {
  id: string
  label: string
  description?: string
  provider?: string
  tag?: string
}

export interface ModelSearchGroup {
  name: string
  models: ModelSearchOption[]
}

export const PROFILE_GROUP = 'Profiles'

const PROVIDER_PREFIXES: Array<{ prefix: string; group: string }> = [
  { prefix: 'gpt-', group: 'openai' },
  { prefix: 'chatgpt', group: 'openai' },
  { prefix: 'o1', group: 'openai' },
  { prefix: 'o3', group: 'openai' },
  { prefix: 'o4', group: 'openai' },
  { prefix: 'claude-', group: 'anthropic' },
  { prefix: 'gemini-', group: 'gemini' },
  { prefix: 'gemma-', group: 'gemini' },
  { prefix: 'deepseek', group: 'deepseek' },
  { prefix: 'llama', group: 'ollama' },
  { prefix: 'mistral', group: 'mistral' },
  { prefix: 'grok', group: 'xai' },
]

const KNOWN_GROUP_ORDER = [
  'openai',
  'anthropic',
  'gemini',
  'xai',
  'deepseek',
  'mistral',
  'ollama',
]

export function modelProviderGroup(id: string, explicit?: string): string {
  const fromExplicit = (explicit || '').trim()
  if (fromExplicit) return fromExplicit
  const raw = id.trim()
  if (!raw) return PROFILE_GROUP
  const slash = raw.indexOf('/')
  if (slash > 0) return raw.slice(0, slash)
  const lower = raw.toLowerCase()
  for (const { prefix, group } of PROVIDER_PREFIXES) {
    if (lower.startsWith(prefix)) return group
  }
  return PROFILE_GROUP
}

export function filterModelOptions(
  models: readonly ModelSearchOption[],
  query: string,
): ModelSearchOption[] {
  const q = query.trim().toLowerCase()
  if (!q) return [...models]
  return models.filter((row) => {
    const group = modelProviderGroup(row.id, row.provider)
    const hay = [row.id, row.label, row.description || '', row.provider || '', row.tag || '', group]
      .join(' ')
      .toLowerCase()
    if (hay.includes(q)) return true
    if (row.id.toLowerCase().startsWith(q)) return true
    if (`${group}/`.startsWith(q) || `${group}-`.startsWith(q)) return true
    return false
  })
}

export function groupModelOptions(
  models: readonly ModelSearchOption[],
): ModelSearchGroup[] {
  const map = new Map<string, ModelSearchOption[]>()
  for (const row of models) {
    const name = modelProviderGroup(row.id, row.provider)
    const list = map.get(name) ?? []
    list.push(row)
    map.set(name, list)
  }
  const names = [...map.keys()]
  names.sort((a, b) => {
    if (a === PROFILE_GROUP && b !== PROFILE_GROUP) return 1
    if (b === PROFILE_GROUP && a !== PROFILE_GROUP) return -1
    const ia = KNOWN_GROUP_ORDER.indexOf(a)
    const ib = KNOWN_GROUP_ORDER.indexOf(b)
    if (ia !== -1 || ib !== -1) {
      return (ia === -1 ? 1000 : ia) - (ib === -1 ? 1000 : ib)
    }
    return a.localeCompare(b)
  })
  return names.map((name) => ({ name, models: map.get(name)! }))
}
