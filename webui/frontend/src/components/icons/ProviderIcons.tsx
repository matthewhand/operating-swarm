/**
 * #1249 — brand-accurate provider / CLI marks.
 *
 * These are deliberately compact, `currentColor`-driven geometric takes on
 * each provider's public mark (a flower for OpenAI, an asterisk for Anthropic,
 * a four-point spark for Gemini, …). They stay license-safe: no trademark
 * artwork is copied verbatim, only the recognisable silhouette is evoked so
 * the routing pill and provider palette read as the concrete provider rather
 * than a generic Lucide glyph.
 *
 * `providerIconFor(id)` is the slug-keyed resolver used by provider surfaces
 * that carry a bare provider/CLI id (e.g. `provider/openai`, `opencode-go`,
 * `cli:claude`). It always returns a component — unknown ids fall back to a
 * neutral gateway mark, never a crash.
 */
import type { ComponentType, ReactNode, SVGProps } from 'react'

export type ProviderIconProps = SVGProps<SVGSVGElement>

function BrandSvg({ children, ...props }: ProviderIconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  )
}

/** OpenAI — six-petal rosette. */
export function OpenAIIcon(props: ProviderIconProps) {
  return (
    <BrandSvg {...props}>
      {[0, 60, 120, 180, 240, 300].map((angle) => (
        <path
          key={angle}
          d="M12 3.4c1.9 1.9 1.9 4.8 0 6.7-1.9-1.9-1.9-4.8 0-6.7Z"
          transform={`rotate(${angle} 12 12)`}
        />
      ))}
    </BrandSvg>
  )
}

/** Anthropic / Claude — six-spoke asterisk. */
export function AnthropicIcon(props: ProviderIconProps) {
  return (
    <BrandSvg {...props}>
      <path d="M12 3.5v17" />
      <path d="M4.6 7.75 19.4 16.25" />
      <path d="M19.4 7.75 4.6 16.25" />
    </BrandSvg>
  )
}

/** Google / Gemini — four-point spark. */
export function GoogleIcon(props: ProviderIconProps) {
  return (
    <BrandSvg {...props}>
      <path
        d="M12 2.4 14.1 9.9 21.6 12 14.1 14.1 12 21.6 9.9 14.1 2.4 12 9.9 9.9Z"
        fill="currentColor"
        stroke="none"
      />
    </BrandSvg>
  )
}

/** xAI / Grok — slashed X. */
export function XAIIcon(props: ProviderIconProps) {
  return (
    <BrandSvg {...props}>
      <path d="M4 4 20 20" />
      <path d="M20 4 4 20" />
    </BrandSvg>
  )
}

/** OpenCode — terminal prompt. */
export function OpenCodeIcon(props: ProviderIconProps) {
  return (
    <BrandSvg {...props}>
      <rect x="3" y="4.5" width="18" height="15" rx="3" />
      <path d="M7.5 10 10.5 12.5 7.5 15" />
      <path d="M13 15h4" />
    </BrandSvg>
  )
}

/** DeepSeek — whale. */
export function DeepSeekIcon(props: ProviderIconProps) {
  return (
    <BrandSvg {...props}>
      <path d="M3.2 13.4c.7-3.3 4.2-6 8.3-6 2.6 0 4.9 1 6.4 2.6.9.9 1.6 1.6 2.1 1.2.1 2.6-1.9 4.8-4.7 4.8H7.9c-2.6 0-4.7-1.1-4.7-2.6Z" />
      <circle cx="8.2" cy="12.4" r="0.9" fill="currentColor" stroke="none" />
    </BrandSvg>
  )
}

/** Mistral — stepped pixel bars. */
export function MistralIcon(props: ProviderIconProps) {
  return (
    <BrandSvg {...props}>
      <rect x="3" y="4.5" width="18" height="3.4" rx="0.6" fill="currentColor" stroke="none" />
      <rect x="3" y="10.3" width="12.5" height="3.4" rx="0.6" fill="currentColor" stroke="none" />
      <rect x="8.5" y="16.1" width="12.5" height="3.4" rx="0.6" fill="currentColor" stroke="none" />
    </BrandSvg>
  )
}

/** Meta / Llama — interlocking loops. */
export function MetaIcon(props: ProviderIconProps) {
  return (
    <BrandSvg {...props}>
      <circle cx="9" cy="12" r="4.6" />
      <circle cx="15" cy="12" r="4.6" />
    </BrandSvg>
  )
}

/** Ollama — llama face. */
export function OllamaIcon(props: ProviderIconProps) {
  return (
    <BrandSvg {...props}>
      <path d="M9 4v2.5" />
      <path d="M13 4v2.5" />
      <path d="M8 6.5h6v3.5h1.5A2.5 2.5 0 0 1 18 12.5V18a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3v-5.5A2.5 2.5 0 0 1 7.5 10H8Z" />
      <circle cx="10" cy="14" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="14" cy="14" r="0.8" fill="currentColor" stroke="none" />
    </BrandSvg>
  )
}

/** LiteLLM — routing gateway. */
export function LiteLLMIcon(props: ProviderIconProps) {
  return (
    <BrandSvg {...props}>
      <rect x="3" y="4.5" width="18" height="15" rx="3" />
      <path d="M7.5 9h9" />
      <path d="M7.5 15h9" />
      <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" />
    </BrandSvg>
  )
}

/** Groq — bolt in a rounded tile. */
export function GroqIcon(props: ProviderIconProps) {
  return (
    <BrandSvg {...props}>
      <rect x="3" y="3" width="18" height="18" rx="4" />
      <path d="M13.5 8 9 13h4l-1.5 4 5-5.5h-4Z" fill="currentColor" stroke="none" />
    </BrandSvg>
  )
}

/** OpenRouter — routing chevrons. */
export function OpenRouterIcon(props: ProviderIconProps) {
  return (
    <BrandSvg {...props}>
      <path d="M5 8l6 4-6 4" />
      <path d="M13 8l6 4-6 4" />
    </BrandSvg>
  )
}

/** Neutral fallback — a gateway cube for unknown providers. */
export function GenericProviderIcon(props: ProviderIconProps) {
  return (
    <BrandSvg {...props}>
      <path d="M12 3 20 7.5v9L12 21 4 16.5v-9Z" />
      <path d="M4 7.5 12 12l8-4.5" />
      <path d="M12 12v9" />
    </BrandSvg>
  )
}

export type ProviderBrand =
  | 'openai'
  | 'anthropic'
  | 'google'
  | 'xai'
  | 'opencode'
  | 'deepseek'
  | 'mistral'
  | 'meta'
  | 'ollama'
  | 'litellm'
  | 'groq'
  | 'openrouter'
  | 'generic'

const PROVIDER_BRANDS: Record<string, ProviderBrand> = {
  openai: 'openai',
  'open-ai': 'openai',
  gpt: 'openai',
  chatgpt: 'openai',
  anthropic: 'anthropic',
  claude: 'anthropic',
  google: 'google',
  gemini: 'google',
  vertex: 'google',
  'vertex-ai': 'google',
  xai: 'xai',
  grok: 'xai',
  opencode: 'opencode',
  'opencode-go': 'opencode',
  deepseek: 'deepseek',
  mistral: 'mistral',
  mixtral: 'mistral',
  codestral: 'mistral',
  meta: 'meta',
  llama: 'meta',
  'meta-llama': 'meta',
  ollama: 'ollama',
  litellm: 'litellm',
  'lite-llm': 'litellm',
  groq: 'groq',
  openrouter: 'openrouter',
}

/**
 * Resolve a provider/CLI slug to a brand. Strips a `provider/` prefix and a
 * seat-kind prefix (`cli:`, `remote:`, `team:`, `blueprint:`, `api:`), then
 * falls back to the leading slug segment so versioned ids (`grok-4`,
 * `gemini-2.0`) still resolve.
 */
export function providerBrandFor(id?: string | null): ProviderBrand {
  const raw = (id || '').trim().toLowerCase()
  if (!raw) return 'generic'
  if (PROVIDER_BRANDS[raw]) return PROVIDER_BRANDS[raw]
  const slug = raw
    .replace(/^provider\//, '')
    .replace(/^(cli|remote|team|blueprint|api):/, '')
  if (PROVIDER_BRANDS[slug]) return PROVIDER_BRANDS[slug]
  const head = slug.split(/[\s/:_-]+/)[0]
  return PROVIDER_BRANDS[head] ?? 'generic'
}

const BRAND_ICONS: Record<ProviderBrand, ComponentType<ProviderIconProps>> = {
  openai: OpenAIIcon,
  anthropic: AnthropicIcon,
  google: GoogleIcon,
  xai: XAIIcon,
  opencode: OpenCodeIcon,
  deepseek: DeepSeekIcon,
  mistral: MistralIcon,
  meta: MetaIcon,
  ollama: OllamaIcon,
  litellm: LiteLLMIcon,
  groq: GroqIcon,
  openrouter: OpenRouterIcon,
  generic: GenericProviderIcon,
}

/** Component for a provider slug; unknown ids get the neutral fallback. */
export function providerIconFor(id?: string | null): ComponentType<ProviderIconProps> {
  return BRAND_ICONS[providerBrandFor(id)]
}
