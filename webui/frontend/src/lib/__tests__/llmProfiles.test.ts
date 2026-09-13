import { describe, expect, it } from 'vitest'
import type { LlmProfilesSettings } from '../api'
import {
  buildLlmProfileEntry,
  effectiveTaskProfile,
  isKnownProfile,
  missingProfileWarning,
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
      api_key: '${GROQ_API_KEY}',
      base_url: 'https://api.groq.com/openai/v1',
    })
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

  it('strips REQ and Issue numbers from UI status copy', () => {
    const cleaned = sanitizeUiWarning('No connected cli_agents; skipped REQ-44 list-models probe.')
    expect(cleaned).not.toMatch(/REQ-\d+|#\d+|Issue\s+\d+/i)
    expect(cleaned.toLowerCase()).toMatch(/cli/)
    expect(uiStatusWarnings(['skipped REQ-44 list-models probe.', 'No CLI agents connected — add a CLI to list models'])).toEqual([
      'skipped list-models probe',
      'No CLI agents connected — add a CLI to list models',
    ])
  })
})
