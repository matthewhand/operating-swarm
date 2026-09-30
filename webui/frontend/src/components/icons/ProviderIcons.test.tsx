/**
 * #1249 — brand icon resolver.
 *
 * `providerIconFor(id)` is slug-keyed: provider surfaces hand it a bare id
 * (`provider/openai`, `opencode-go`, `cli:claude`) and it must resolve the
 * matching brand mark, falling back to the neutral gateway for anything
 * unknown — never throwing.
 */
import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import {
  AnthropicIcon,
  DeepSeekIcon,
  GenericProviderIcon,
  GoogleIcon,
  GroqIcon,
  LiteLLMIcon,
  MetaIcon,
  MistralIcon,
  OllamaIcon,
  OpenAIIcon,
  OpenCodeIcon,
  OpenRouterIcon,
  XAIIcon,
  providerBrandFor,
  providerIconFor,
} from './ProviderIcons'

describe('#1249 providerIconFor resolver', () => {
  it('resolves known provider slugs to their brand mark', () => {
    expect(providerIconFor('openai')).toBe(OpenAIIcon)
    expect(providerIconFor('anthropic')).toBe(AnthropicIcon)
    expect(providerIconFor('claude')).toBe(AnthropicIcon)
    expect(providerIconFor('gemini')).toBe(GoogleIcon)
    expect(providerIconFor('google')).toBe(GoogleIcon)
    expect(providerIconFor('grok')).toBe(XAIIcon)
    expect(providerIconFor('xai')).toBe(XAIIcon)
    expect(providerIconFor('opencode')).toBe(OpenCodeIcon)
    expect(providerIconFor('deepseek')).toBe(DeepSeekIcon)
    expect(providerIconFor('mistral')).toBe(MistralIcon)
    expect(providerIconFor('llama')).toBe(MetaIcon)
    expect(providerIconFor('meta')).toBe(MetaIcon)
    expect(providerIconFor('ollama')).toBe(OllamaIcon)
    expect(providerIconFor('litellm')).toBe(LiteLLMIcon)
    expect(providerIconFor('groq')).toBe(GroqIcon)
    expect(providerIconFor('openrouter')).toBe(OpenRouterIcon)
  })

  it('strips the provider/ prefix and handles opencode-go', () => {
    expect(providerIconFor('provider/openai')).toBe(OpenAIIcon)
    expect(providerIconFor('provider/anthropic')).toBe(AnthropicIcon)
    expect(providerIconFor('opencode-go')).toBe(OpenCodeIcon)
  })

  it('strips seat-kind prefixes and version suffixes', () => {
    expect(providerIconFor('cli:claude')).toBe(AnthropicIcon)
    expect(providerIconFor('api:gpt-4o')).toBe(OpenAIIcon)
    expect(providerIconFor('grok-4')).toBe(XAIIcon)
    expect(providerIconFor('gemini-2.0-flash')).toBe(GoogleIcon)
  })

  it('falls back to the neutral mark for unknown ids', () => {
    expect(providerIconFor('acme-corp')).toBe(GenericProviderIcon)
    expect(providerIconFor('remote:herdr')).toBe(GenericProviderIcon)
    expect(providerIconFor('')).toBe(GenericProviderIcon)
    expect(providerIconFor(undefined)).toBe(GenericProviderIcon)
    expect(providerBrandFor('acme-corp')).toBe('generic')
  })

  it('the fallback renders a currentColor svg', () => {
    const { container } = render(<GenericProviderIcon className="w-4 h-4" />)
    const svg = container.querySelector('svg')
    expect(svg).not.toBeNull()
    expect(svg?.getAttribute('stroke')).toBe('currentColor')
    expect(svg?.getAttribute('aria-hidden')).toBe('true')
  })
})
