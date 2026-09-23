/** #856 slice A — llm endpoints (moved verbatim from lib/api.ts). */
import {
  apiGet,
  apiPatch,
  apiPost,
} from './client'
import type {
  ListResponse,
  Model,
  RateLimitRules,
  RateLimitsPayload,
  SupportContext,
} from './types'

export function fetchSupportContext(): Promise<SupportContext> {
  return apiGet<SupportContext>('/v1/support/context/')
}
/** GET /v1/runtime/ — REQ-45 app runtime banner (AllowAny, no secrets). */
export function fetchRuntimeBanner(): Promise<Record<string, unknown>> {
  return apiGet<Record<string, unknown>>('/v1/runtime/')
}
/** GET /v1/browser-control/ — REQ-45 provider catalog (this-machine default). */
export function fetchBrowserControl(): Promise<Record<string, unknown>> {
  return apiGet<Record<string, unknown>>('/v1/browser-control/')
}
export function fetchModels(): Promise<ListResponse<Model>> {
  return apiGet<ListResponse<Model>>('/v1/models/')
}
/** Task-class roles for REQ-43 (+ #858/#859/#860 inference overrides). These are not required model ids. */
export const LLM_TASK_CLASSES = [
  'orchestration',
  'auxiliary',
  'delegation',
  'tiny',
  'compaction',
  'autocomplete',
] as const
/** #858: Expand and refine a draft prompt via the tiny model. */
export async function enhancePrompt(
  prompt: string,
): Promise<{ prompt: string; enhanced: string }> {
  return apiPost<{ prompt: string; enhanced: string }>('/v1/assist/enhance-prompt', { prompt })
}
/** #860: Inline ghost-text completion for the composer. */
export async function fetchAutocomplete(
  prefix: string,
  opts?: {
    suffix?: string
    agent_id?: string
    conversation_id?: string
    max_tokens?: number
  },
): Promise<{ completion: string; duration_ms: number }> {
  return apiPost<{ completion: string; duration_ms: number }>('/v1/chat/autocomplete', {
    prefix,
    ...opts,
  })
}
export function fetchRateLimits(): Promise<RateLimitsPayload> {
  return apiGet<RateLimitsPayload>('/v1/rate-limits/')
}
export function patchRateLimits(
  provider: string,
  rules: Partial<RateLimitRules>,
): Promise<RateLimitsPayload> {
  return apiPatch<RateLimitsPayload>('/v1/rate-limits/', { provider, rules })
}
export type LlmTaskClass = (typeof LLM_TASK_CLASSES)[number]
