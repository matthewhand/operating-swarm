/**
 * #795 — one provider-icon registry for the composer routing pill.
 *
 * The lookup is semantic, not brand-faithful: remote harness kinds and LLM
 * providers resolve to a compact Lucide glyph stamped with
 * `data-provider-icon=<resolved key>` so tests and CSS can key off the
 * concrete provider without importing brand SVGs. Fallbacks are explicit:
 * kind icons (team/cli/api) and, last, the generic `api` glyph.
 */
import type { ReactNode } from 'react'
import {
  Bot,
  Brain,
  Cpu,
  Boxes,
  Globe,
  Hash,
  Layers,
  MessageSquare,
  Network,
  Sparkles,
  Terminal,
  TerminalSquare,
  Users,
  Workflow,
  Zap,
} from 'lucide-react'

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
  | 'herdr'
  | 'omb'
  | 'hermes'
  | 'letta'
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
  bedrock: 'api',
  localai: 'api',

  // Remote harness kinds (remote seats) — superset of REMOTE_KIND_LABELS
  hermes: 'hermes',
  anythingllm: 'anythingllm',
  letta: 'letta',
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
    if (/groq/.test(model)) return 'groq'
  }

  return 'api'
}

const GLYPHS: Record<ProviderIconKey, typeof Bot> = {
  anthropic: Sparkles,
  openai: Zap,
  google: Sparkles,
  ollama: Boxes,
  groq: Zap,
  mistral: Sparkles,
  openrouter: Network,
  deepseek: Brain,
  herdr: Terminal,
  omb: Bot,
  hermes: MessageSquare,
  letta: Brain,
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
