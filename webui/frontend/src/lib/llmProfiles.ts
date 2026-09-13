/**
 * Settings LLM profiles (REQ-43 / #358).
 *
 * Persistence is the server SoT (`settings.default_llm_profile`). This module
 * only types the payload and flags missing picks for the SPA warning.
 */

import {
  LLM_TASK_CLASSES,
  type LlmProfile,
  type LlmProfilesSettings,
  type LlmTaskClass,
} from './api'

export { LLM_TASK_CLASSES }
export type { LlmProfile, LlmProfilesSettings, LlmTaskClass }

export const TASK_CLASS_LABELS: Record<LlmTaskClass, string> = {
  orchestration: 'User chat / orchestration',
  auxiliary: 'Auxiliary (code summary)',
  delegation: 'Delegation (design / coding)',
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

/** Short add-profile form. Advanced (temperature / max tokens / timeout) stays collapsed. */
export const LLM_PROFILE_PROVIDERS = [
  'openai',
  'azure',
  'anthropic',
  'groq',
  'ollama',
  'openrouter',
] as const

export interface LlmProfileDraft {
  name: string
  provider: string
  model: string
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
