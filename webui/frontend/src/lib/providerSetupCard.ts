/**
 * #894 — parse the bootstrap agent's in-chat provider setup card.
 *
 * The deterministic bootstrap Admin/Support seat (#893) emits a fenced JSON
 * block in its reply (same pattern as REQ-158's NL-blueprint cards):
 *
 * ```swarm-provider-setup
 * {"type": "provider_setup", "default_provider": "openai"}
 * ```
 *
 * The bubble splits the fence out of the prose and renders the interactive
 * {@link ../components/ProviderSetupCard} in its place. Malformed JSON, a
 * missing type, or a foreign `type` never yields a card — the fence then
 * renders as plain text rather than a broken form.
 */

export const PROVIDER_SETUP_FENCE = 'swarm-provider-setup'

const FENCE_RE = /```swarm-provider-setup\s*\n([\s\S]*?)```/i

export interface ProviderSetupCardSpec {
  type: 'provider_setup'
  defaultProvider?: string
}

export interface ProviderPreset {
  id: string
  label: string
  group: 'cloud' | 'local'
  baseUrl: string
  defaultModel: string
  apiKeyEnv: string
  needsKey: boolean
}

/** Popular presets per #894 — cloud APIs and local/self-hosted gateways. */
export const PROVIDER_PRESETS: readonly ProviderPreset[] = [
  { id: 'openai', label: 'OpenAI', group: 'cloud', baseUrl: 'https://api.openai.com/v1', defaultModel: 'gpt-4o', apiKeyEnv: 'OPENAI_API_KEY', needsKey: true },
  { id: 'anthropic', label: 'Anthropic', group: 'cloud', baseUrl: 'https://api.anthropic.com/v1', defaultModel: 'claude-3-5-sonnet', apiKeyEnv: 'ANTHROPIC_API_KEY', needsKey: true },
  { id: 'groq', label: 'Groq', group: 'cloud', baseUrl: 'https://api.groq.com/openai/v1', defaultModel: 'llama-3.3-70b-versatile', apiKeyEnv: 'GROQ_API_KEY', needsKey: true },
  { id: 'openrouter', label: 'OpenRouter', group: 'cloud', baseUrl: 'https://openrouter.ai/api/v1', defaultModel: 'openai/gpt-4o', apiKeyEnv: 'OPENROUTER_API_KEY', needsKey: true },
  { id: 'mistral', label: 'Mistral', group: 'cloud', baseUrl: 'https://api.mistral.ai/v1', defaultModel: 'mistral-large-latest', apiKeyEnv: 'MISTRAL_API_KEY', needsKey: true },
  { id: 'ollama', label: 'Ollama', group: 'local', baseUrl: 'http://localhost:11434/v1', defaultModel: 'llama3.1:8b', apiKeyEnv: 'OLLAMA_API_KEY', needsKey: false },
  { id: 'lmstudio', label: 'LM Studio', group: 'local', baseUrl: 'http://localhost:1234/v1', defaultModel: 'local-model', apiKeyEnv: 'LMSTUDIO_API_KEY', needsKey: false },
  { id: 'vllm', label: 'vLLM', group: 'local', baseUrl: 'http://localhost:8000/v1', defaultModel: 'deepseek-r1', apiKeyEnv: 'VLLM_API_KEY', needsKey: false },
  { id: 'openwebui', label: 'OpenWebUI', group: 'local', baseUrl: 'http://localhost:3000/api/v1', defaultModel: 'local-model', apiKeyEnv: 'OPENWEBUI_API_KEY', needsKey: false },
  { id: 'localai', label: 'LocalAI', group: 'local', baseUrl: 'http://localhost:8080/v1', defaultModel: 'gpt-4o', apiKeyEnv: 'LOCALAI_API_KEY', needsKey: false },
]

export function providerPresetById(id: string): ProviderPreset | null {
  const needle = id.trim().toLowerCase()
  return PROVIDER_PRESETS.find((preset) => preset.id === needle) ?? null
}

export function parseProviderSetupFence(text: string): {
  prose: string
  card: ProviderSetupCardSpec | null
} {
  const source = String(text ?? '')
  const match = source.match(FENCE_RE)
  if (!match) {
    return { prose: source, card: null }
  }
  let card: ProviderSetupCardSpec | null = null
  try {
    const data = JSON.parse(match[1] || '') as Record<string, unknown>
    if (String(data.type || '') === 'provider_setup') {
      card = {
        type: 'provider_setup',
        defaultProvider:
          typeof data.default_provider === 'string' && data.default_provider.trim()
            ? data.default_provider.trim().toLowerCase()
            : 'openai',
      }
    }
  } catch {
    card = null
  }
  const prose = card
    ? `${source.slice(0, match.index)}${source.slice((match.index || 0) + match[0].length)}`
        .replace(/\n{3,}/g, '\n\n')
        .trim()
    : source
  return { prose, card }
}
