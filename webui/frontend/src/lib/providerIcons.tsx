/**
 * #795 / #1249 — one provider-icon registry for the composer routing pill.
 *
 * LLM providers resolve to brand-accurate mark components
 * (`components/icons/ProviderIcons.tsx`) while remote harness kinds keep a
 * compact Lucide glyph. Every rendered icon is stamped with
 * `data-provider-icon=<resolved key>` so tests and CSS can key off the
 * concrete provider. Fallbacks are explicit: kind icons (team/cli/api) and,
 * last, the generic `api` glyph.
 */
import type { ComponentType, ReactNode } from 'react'
import {
  Bot,
  Brain,
  Cpu,
  Boxes,
  Globe,
  Hash,
  Layers,
  MessageSquare,
  Terminal,
  TerminalSquare,
  Users,
  Workflow,
} from 'lucide-react'

import {
  AnthropicIcon,
  DeepSeekIcon,
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
  type ProviderIconProps,
} from '../components/icons/ProviderIcons'

import type { RoutingSeatKind } from '../lib/routingPath'

export type ProviderIconKey =
  | 'anthropic'
  | 'openai'
  | 'google'
  | 'ollama'
  | 'groq'
  | 'mistral'
  | 'openrouter'
  | 'deepseek'
  | 'xai'
  | 'opencode'
  | 'meta'
  | 'litellm'
  | 'herdr'
  | 'omb'
  | 'hermes'
  | 'openwebui'
  | 'flowise'
  | 'n8n'
  | 'rakazo'
  | 'swarm'
  | 'trueforge'
  | 'anythingllm'
  | 'slack'
  | 'team'
  | 'cli'
  | 'api'

const PROVIDER_KEYS: Record<string, ProviderIconKey> = {
  // LLM providers (api seats)
  anthropic: 'anthropic',
  claude: 'anthropic',
  openai: 'openai',
  gpt: 'openai',
  google: 'google',
  gemini: 'google',
  vertex: 'google',
  ollama: 'ollama',
  groq: 'groq',
  mistral: 'mistral',
  openrouter: 'openrouter',
  deepseek: 'deepseek',
  xai: 'xai',
  grok: 'xai',
  opencode: 'opencode',
  'opencode-go': 'opencode',
  meta: 'meta',
  llama: 'meta',
  litellm: 'litellm',
  'lite-llm': 'litellm',
  bedrock: 'api',
  localai: 'api',

  // Remote harness kinds (remote seats) — superset of REMOTE_KIND_LABELS
  hermes: 'hermes',
  anythingllm: 'anythingllm',
  openwebui: 'openwebui',
  flowise: 'flowise',
  n8n: 'n8n',
  omb: 'omb',
  openmousbot: 'omb',
  openmausbot: 'omb',
  openmous: 'omb',
  rakazo: 'rakazo',
  rakezo: 'rakazo',
  herdr: 'herdr',
  swarm: 'swarm',
  'open-swarm': 'swarm',
  trueforge: 'trueforge',
  slack: 'slack',
}

export interface ProviderIconInput {
  seatKind: RoutingSeatKind
  /** Provider / harness id (e.g. `herdr`, `anthropic`). */
  providerId?: string
  /** Model id — consulted when the provider id is generic or empty. */
  modelId?: string
  className?: string
}

/** Resolve the semantic icon key for a seat/provider/model triple. */
export function providerIconKey({
  seatKind,
  providerId,
  modelId,
}: Omit<ProviderIconInput, 'className'>): ProviderIconKey {
  const key = (providerId || '').trim().toLowerCase()

  if (key) {
    const direct = PROVIDER_KEYS[key]
    if (direct) return direct
    // CLI seats named after a provider-ish id still resolve: `claude` CLI,
    // `gemini` CLI, `grok`/`agy`/`codex`/`opencode`/`qwen` → cli glyph.
    const head = key.split(/[\s_:-]/)[0]
    const viaHead = PROVIDER_KEYS[head]
    if (viaHead) return viaHead
  }

  if (seatKind === 'team') return 'team'
  if (seatKind === 'cli') return 'cli'

  // Generic provider id but a recognizable model family (e.g. the api_agent
  // seat running `claude-…`): infer from the model string.
  const model = (modelId || '').trim().toLowerCase()
  if (model) {
    if (/claude/.test(model)) return 'anthropic'
    if (/^(gpt|o\d|davinci|chatgpt)/.test(model)) return 'openai'
    if (/gemini|palm|bard/.test(model)) return 'google'
    if (/llama/.test(model)) return 'ollama'
    if (/mistral|mixtral|codestral/.test(model)) return 'mistral'
    if (/deepseek/.test(model)) return 'deepseek'
    if (/grok/.test(model)) return 'xai'
    if (/opencode/.test(model)) return 'opencode'
    if (/groq/.test(model)) return 'groq'
  }

  return 'api'
}

const GLYPHS: Record<ProviderIconKey, ComponentType<ProviderIconProps>> = {
  anthropic: AnthropicIcon,
  openai: OpenAIIcon,
  google: GoogleIcon,
  ollama: OllamaIcon,
  groq: GroqIcon,
  mistral: MistralIcon,
  openrouter: OpenRouterIcon,
  deepseek: DeepSeekIcon,
  xai: XAIIcon,
  opencode: OpenCodeIcon,
  meta: MetaIcon,
  litellm: LiteLLMIcon,
  herdr: Terminal,
  omb: Bot,
  hermes: MessageSquare,
  openwebui: Globe,
  flowise: Workflow,
  n8n: Workflow,
  rakazo: Layers,
  swarm: Users,
  trueforge: Boxes,
  anythingllm: Brain,
  slack: Hash,
  team: Users,
  cli: TerminalSquare,
  api: Cpu,
}

/** Render the resolved provider glyph (an svg, or null only if key unknown). */
export function getProviderIcon({
  seatKind,
  providerId,
  modelId,
  className,
}: ProviderIconInput): ReactNode {
  const key = providerIconKey({ seatKind, providerId, modelId })
  const Glyph = GLYPHS[key] ?? Cpu
  return (
    <Glyph
      className={className}
      aria-hidden="true"
      data-provider-icon={key}
    />
  )
}
