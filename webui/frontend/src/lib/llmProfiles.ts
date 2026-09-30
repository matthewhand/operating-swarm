/**
 * Settings LLM profiles (REQ-43 / #358).
 *
 * Persistence is the server SoT (`settings.default_llm_profile`). This module
 * only types the payload and flags missing picks for the SPA warning.
 */

import {
  LLM_TASK_CLASSES,
  type LlmModelType,
  type LlmProfile,
  type LlmProfilesSettings,
  type LlmTaskClass,
} from './api'
import { providerPresetById } from './providerSetupCard'

export { LLM_TASK_CLASSES }
export type { LlmModelType, LlmProfile, LlmProfilesSettings, LlmTaskClass }

export const TASK_CLASS_LABELS: Record<LlmTaskClass, string> = {
  orchestration: 'User chat / orchestration',
  auxiliary: 'Auxiliary (code summary & session labelling)',
  delegation: 'Delegation (design / coding)',
  tiny: 'Tiny (titles / commit messages)',
  compaction: 'Compaction (long-context summary)',
  autocomplete: 'Autocomplete (inline ghost text)',
}

export function profileIds(settings: LlmProfilesSettings | null | undefined): string[] {
  return (settings?.profiles ?? []).map((profile) => profile.id)
}

export function isKnownProfile(
  id: string | undefined,
  settings: LlmProfilesSettings | null | undefined,
): boolean {
  if (!id) return false
  return profileIds(settings).includes(id)
}

const TICKET_JARGON = /\(?\bREQ-\d+\b\)?|\(?\bIssue\s+#?\d+\b\)?|#\d+\b/gi

/** Strip REQ/Issue ticket jargon from Settings status lines. */
export function sanitizeUiWarning(text: string): string {
  return text
    .replace(TICKET_JARGON, ' ')
    .replace(/\s{2,}/g, ' ')
    .replace(/^[\s;,.–—-]+|[\s;,.–—-]+$/g, '')
    .trim()
}

/** UI-only status lines — never feed these into LLM context. */
export function uiStatusWarnings(warnings: string[] | undefined | null): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of warnings ?? []) {
    const cleaned = sanitizeUiWarning(raw)
    if (!cleaned || seen.has(cleaned)) continue
    seen.add(cleaned)
    out.push(cleaned)
  }
  return out
}

export function missingProfileWarning(
  id: string | undefined,
  settings: LlmProfilesSettings | null | undefined,
  fallback: string,
): string | null {
  if (!id) return null
  if (isKnownProfile(id, settings)) return null
  return `Profile ${id} is not in the connected catalog; falling back to ${fallback}.`
}

export function effectiveTaskProfile(
  taskClass: LlmTaskClass,
  settings: LlmProfilesSettings | null | undefined,
): string {
  const fallback = settings?.default_llm_profile || 'default'
  if (!settings?.override_per_task) return fallback
  return settings.task_llm_profiles?.[taskClass] || fallback
}

// --- #1745 — System1 is a model type, not a hidden OpenAI-compat base URL ---

/** The OpenRig vendor id. A first-class entry, not a custom-endpoint hack. */
export const SYSTEM1_PROVIDER_ID = 'system1'
/** Env *names* only. The System1 Service owns reachability and credentials. */
export const SYSTEM1_BASE_URL_ENV = 'SYSTEM1_BASE_URL'
export const SYSTEM1_API_KEY_ENV = 'SYSTEM1_API_KEY'

/** Short add-profile form. Advanced (temperature / max tokens / timeout) stays collapsed. */
export const LLM_PROFILE_PROVIDERS = [
  'openai',
  'azure',
  'anthropic',
  'groq',
  'ollama',
  'openrouter',
  'mistral',
  SYSTEM1_PROVIDER_ID,
] as const

export const LLM_MODEL_TYPES: readonly LlmModelType[] = ['chat', 'categorizer']

/**
 * Operator-facing copy. "System1" and "categorizer / gate" both appear, so the
 * row is recognisable whether the operator thinks in OpenRig or in seats.
 */
export const MODEL_TYPE_LABELS: Record<LlmModelType, string> = {
  chat: 'Chat LLM',
  categorizer: 'System1 (categorizer / gate)',
}

export const MODEL_TYPE_DESCRIPTIONS: Record<LlmModelType, string> = {
  chat: 'Emits chat tokens. Serves user chat and task-class jobs.',
  categorizer:
    'Answers a gate question (allow / deny) for filter-in / filter-out seats. Never offered as a chat model.',
}

/** Unknown / missing ⇒ `chat`, mirroring the backend normaliser. */
export function normalizeModelType(value: unknown): LlmModelType {
  const key = String(value ?? '').trim().toLowerCase()
  if (!key) return 'chat'
  if (
    key === 'categorizer' ||
    key === 'system1' ||
    key === 'system-1' ||
    key === 'system_1' ||
    key === 'classifier' ||
    key === 'classify' ||
    key === 'gate' ||
    key === 'gating' ||
    key === 'filter'
  ) {
    return 'categorizer'
  }
  return 'chat'
}

export function isCategorizerModelType(value: unknown): boolean {
  return normalizeModelType(value) === 'categorizer'
}

/** The model type of a `/v1/llm-profiles/` row. */
export function profileModelType(
  profile: { model_type?: unknown; owned_by?: string } | null | undefined,
): LlmModelType {
  if (!profile) return 'chat'
  if (String(profile.model_type ?? '').trim()) {
    return normalizeModelType(profile.model_type)
  }
  // Older servers omit the key; the System1 vendor still means categorizer.
  return String(profile.owned_by ?? '').trim().toLowerCase() === SYSTEM1_PROVIDER_ID
    ? 'categorizer'
    : 'chat'
}

export function isCategorizerProfile(
  profile: { model_type?: unknown; owned_by?: string } | null | undefined,
): boolean {
  return profileModelType(profile) === 'categorizer'
}

/**
 * Every chat surface routes through here: a System1 gate must never be offered
 * as a chat model, not in the composer picker and not in AgentEditor.
 */
export function chatSelectableProfiles<T extends { model_type?: unknown; owned_by?: string }>(
  profiles: readonly T[] | null | undefined,
): T[] {
  return (profiles ?? []).filter((profile) => !isCategorizerProfile(profile))
}

/** Categorizer rows, for the Settings System1 list. */
export function categorizerProfiles(
  profiles: readonly LlmProfile[] | null | undefined,
): LlmProfile[] {
  return (profiles ?? []).filter((profile) => isCategorizerProfile(profile))
}

export function chatProfiles(
  profiles: readonly LlmProfile[] | null | undefined,
): LlmProfile[] {
  return (profiles ?? []).filter((profile) => !isCategorizerProfile(profile))
}

/** Shared preset defaults (base URL + env var name, never a live key). */
export function defaultsForLlmProvider(provider: string): {
  baseUrl: string
  apiKeyEnv: string
} | null {
  const id = (provider || '').trim().toLowerCase()
  if (id === SYSTEM1_PROVIDER_ID) {
    // The endpoint is an env name too: Open Swarm never stores the URL itself.
    return { baseUrl: `\${${SYSTEM1_BASE_URL_ENV}}`, apiKeyEnv: SYSTEM1_API_KEY_ENV }
  }
  const preset = providerPresetById(provider)
  if (!preset) return null
  return { baseUrl: preset.baseUrl, apiKeyEnv: preset.apiKeyEnv }
}

export type LlmProbeErrorClass =
  | 'auth'
  | 'dns'
  | 'timeout'
  | 'bad_model'
  | 'model_missing'
  | 'ssrf'
  | 'unreachable'
  | 'missing_key'
  | 'invalid'

export type LlmProbeState = 'idle' | 'testing' | 'ok' | 'warn' | 'error'

/** TrueForge-style classified hints. Keep ticket jargon out of the copy. */
export const LLM_PROBE_HINTS: Record<LlmProbeErrorClass, string> = {
  auth: 'check key',
  dns: 'could not resolve host',
  timeout: 'is the host up?',
  bad_model: 'model not found',
  model_missing: 'reachable, but that model is not on the provider',
  ssrf: 'that base URL is not allowed',
  unreachable: 'could not reach host',
  missing_key: 'set the API key env var first',
  invalid: 'base URL is required',
}

export function probeHint(
  errorClass: string | null | undefined,
  fallback = '',
): string {
  if (!errorClass) return fallback
  return LLM_PROBE_HINTS[errorClass as LlmProbeErrorClass] || fallback || errorClass
}

export function probeStateFromResult(result: {
  ok?: boolean
  error_class?: string | null
  state?: string
} | null | undefined): LlmProbeState {
  if (!result) return 'idle'
  if (result.state === 'warn' || result.error_class === 'model_missing') return 'warn'
  if (result.ok) return 'ok'
  return 'error'
}

export interface LlmProfileDraft {
  name: string
  provider: string
  model: string
  /** #1745 omit ⇒ `chat`. `categorizer` registers a System1 gate. */
  modelType?: LlmModelType
  apiKeyEnv?: string
  baseUrl?: string
  temperature?: string
  maxTokens?: string
  timeoutSec?: string
}

function optionalNumber(raw: string | undefined): number | undefined {
  const text = (raw || '').trim()
  if (!text) return undefined
  const n = Number(text)
  return Number.isFinite(n) ? n : undefined
}

/** Persist payload for `PATCH /v1/config/sections/llm/` upsert. Never stores a raw key. */
export function buildLlmProfileEntry(
  draft: Omit<LlmProfileDraft, 'name'>,
): Record<string, unknown> {
  const provider = (draft.provider || 'openai').trim() || 'openai'
  const model = (draft.model || '').trim()
  const envName = (draft.apiKeyEnv || 'OPENAI_API_KEY').trim() || 'OPENAI_API_KEY'
  const entry: Record<string, unknown> = {
    provider,
    model,
    // #1745: the type is stored with the profile, so the operator's choice
    // survives a reload instead of being re-derived from the vendor alone.
    model_type: normalizeModelType(draft.modelType),
    api_key: `\${${envName}}`,
  }
  const base = (draft.baseUrl || '').trim()
  if (base) entry.base_url = base
  const temperature = optionalNumber(draft.temperature)
  if (temperature !== undefined) entry.temperature = temperature
  const maxTokens = optionalNumber(draft.maxTokens)
  if (maxTokens !== undefined) entry.max_tokens = Math.floor(maxTokens)
  const timeout = optionalNumber(draft.timeoutSec)
  if (timeout !== undefined) entry.timeout = timeout
  return entry
}
