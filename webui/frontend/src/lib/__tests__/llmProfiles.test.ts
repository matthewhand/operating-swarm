import { describe, expect, it } from 'vitest'
import type { LlmProfilesSettings } from '../api'
import {
  LLM_PROBE_HINTS,
  LLM_PROFILE_PROVIDERS,
  SYSTEM1_API_KEY_ENV,
  SYSTEM1_BASE_URL_ENV,
  SYSTEM1_PROVIDER_ID,
  buildLlmProfileEntry,
  defaultsForLlmProvider,
  effectiveTaskProfile,
  isKnownProfile,
  missingProfileWarning,
  probeHint,
  probeStateFromResult,
  sanitizeUiWarning,
  uiStatusWarnings,
} from '../llmProfiles'

const settings: LlmProfilesSettings = {
  object: 'llm_profiles',
  profiles: [
    { id: 'gpt-4o-mini', object: 'llm_profile', source: 'config', owned_by: 'openai' },
    { id: 'gpt-5.6-terra', object: 'llm_profile', source: 'config', owned_by: 'openai' },
    { id: 'o3', object: 'llm_profile', source: 'config', owned_by: 'openai' },
  ],
  default_llm_profile: 'gpt-5.6-terra',
  default_is_auto: false,
  override_per_task: true,
  task_llm_profiles: {
    orchestration: 'gpt-5.6-terra',
    auxiliary: 'gpt-4o-mini',
    delegation: 'o3',
  },
  auto_picks: {
    orchestration: 'gpt-5.6-terra',
    auxiliary: 'gpt-4o-mini',
    delegation: 'o3',
    default: 'gpt-5.6-terra',
  },
  warnings: [],
  routes: {},
  task_classes: ['orchestration', 'auxiliary', 'delegation'],
}

describe('llmProfiles helpers', () => {
  it('treats boring ids as known picks', () => {
    expect(isKnownProfile('gpt-5.6-terra', settings)).toBe(true)
    expect(isKnownProfile('missing-slug', settings)).toBe(false)
  })

  it('override off uses Default for every task class', () => {
    const off = { ...settings, override_per_task: false }
    expect(effectiveTaskProfile('auxiliary', off)).toBe('gpt-5.6-terra')
    expect(effectiveTaskProfile('delegation', off)).toBe('gpt-5.6-terra')
  })

  it('override on routes summary to auxiliary and design to delegation', () => {
    expect(effectiveTaskProfile('auxiliary', settings)).toBe('gpt-4o-mini')
    expect(effectiveTaskProfile('delegation', settings)).toBe('o3')
  })

  it('missing slug warns and names the default fallback', () => {
    const warning = missingProfileWarning('missing-slug', settings, 'gpt-5.6-terra')
    expect(warning).toMatch(/missing-slug/)
    expect(warning).toMatch(/gpt-5.6-terra/)
    expect(missingProfileWarning('gpt-4o-mini', settings, 'gpt-5.6-terra')).toBeNull()
  })

  it('lists mistral in the add-profile provider dropdown', () => {
    expect(LLM_PROFILE_PROVIDERS).toContain('mistral')
  })

  it('prefills mistral base URL and MISTRAL_API_KEY from shared defaults', () => {
    expect(defaultsForLlmProvider('mistral')).toEqual({
      baseUrl: 'https://api.mistral.ai/v1',
      apiKeyEnv: 'MISTRAL_API_KEY',
    })
  })

  it('builds a persistable llm upsert from the short add form', () => {
    expect(
      buildLlmProfileEntry({
        provider: 'groq',
        model: 'llama-3.1-8b',
        apiKeyEnv: 'GROQ_API_KEY',
        baseUrl: 'https://api.groq.com/openai/v1',
      }),
    ).toEqual({
      provider: 'groq',
      model: 'llama-3.1-8b',
      // #1745: the model type is persisted with the profile, and a Groq chat
      // model is explicitly `chat` rather than left untyped.
      model_type: 'chat',
      api_key: '${GROQ_API_KEY}',
      base_url: 'https://api.groq.com/openai/v1',
    })
  })

  it('persists a System1 gate as the categorizer type with env-name credentials (#1745)', () => {
    const entry = buildLlmProfileEntry({
      provider: SYSTEM1_PROVIDER_ID,
      model: 'system1-categorizer',
      modelType: 'categorizer',
      apiKeyEnv: SYSTEM1_API_KEY_ENV,
      baseUrl: `\${${SYSTEM1_BASE_URL_ENV}}`,
    })
    expect(entry.model_type).toBe('categorizer')
    expect(entry.api_key).toBe('${SYSTEM1_API_KEY}')
    expect(entry.base_url).toBe('${SYSTEM1_BASE_URL}')
    expect(JSON.stringify(entry)).not.toMatch(/sk-/)
  })

  it('omits collapsed advanced fields until they have values', () => {
    const core = buildLlmProfileEntry({
      provider: 'openai',
      model: 'gpt-4o-mini',
    })
    expect(core).not.toHaveProperty('temperature')
    expect(core).not.toHaveProperty('max_tokens')
    expect(core).not.toHaveProperty('timeout')
    expect(
      buildLlmProfileEntry({
        provider: 'openai',
        model: 'gpt-4o-mini',
        temperature: '0.2',
        maxTokens: '4096',
        timeoutSec: '60',
      }),
    ).toMatchObject({ temperature: 0.2, max_tokens: 4096, timeout: 60 })
  })

  it('maps probe error classes to TrueForge-style hints', () => {
    expect(probeHint('auth')).toBe('check key')
    expect(probeHint('timeout')).toBe('is the host up?')
    expect(probeHint('dns')).toBe('could not resolve host')
    expect(probeHint('bad_model')).toBe('model not found')
    expect(probeHint('model_missing')).toMatch(/not on the provider/)
    expect(probeHint('ssrf')).toMatch(/not allowed/)
    expect(probeHint(null)).toBe('')
    expect(LLM_PROBE_HINTS.auth).toBe('check key')
    expect(JSON.stringify(LLM_PROBE_HINTS)).not.toMatch(/REQ-\d+|#\d+/)
  })

  it('derives form states from probe results', () => {
    expect(probeStateFromResult(undefined)).toBe('idle')
    expect(probeStateFromResult({ ok: true, error_class: null })).toBe('ok')
    expect(probeStateFromResult({ ok: true, error_class: 'model_missing', state: 'warn' })).toBe(
      'warn',
    )
    expect(probeStateFromResult({ ok: false, error_class: 'auth' })).toBe('error')
    expect(probeStateFromResult({ ok: false, error_class: 'unreachable' })).toBe('error')
  })

  it('strips REQ and Issue numbers from UI status copy', () => {
    const cleaned = sanitizeUiWarning('No connected cli_agents; skipped REQ-44 list-models probe.')
    expect(cleaned).not.toMatch(/REQ-\d+|#\d+|Issue\s+\d+/i)
    expect(cleaned.toLowerCase()).toMatch(/cli/)
    expect(uiStatusWarnings(['skipped REQ-44 list-models probe.', 'No CLI agents connected — add a CLI to list models'])).toEqual([
      'skipped list-models probe',
      'No CLI agents connected — add a CLI to list models',
    ])
  })

  it('offers Mistral as a first-class OpenAI-compatible API engine (#1325)', () => {
    expect(LLM_PROFILE_PROVIDERS).toContain('mistral')
    expect(LLM_PROFILE_PROVIDERS).toContain('openai')
  })
})
