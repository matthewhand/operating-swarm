/** #856 slice B — settings kernel (moved verbatim from SettingsSheet.tsx). */
import type { DefinitionKind } from '../../lib/definitionExplain'

export const OPEN_SETTINGS_EVENT = 'swarm:open-settings'

export type SettingsSection =
  | 'general'
  | 'aesthetics'
  | 'providers'
  | 'definition'
  | 'blueprint'
  | 'remotes'
  | 'retention'
  | 'hostname'
  | 'about-me'
  | 'llm-profiles'
  | 'mcp'
  | 'cli-agents'
  | 'roles'
  | 'sandboxes'
  | 'backend-audit'
  | 'seat-doctor'
  | 'operator-activity'
  | 'rail'
  | 'image-gen'
  | 'speech'
  | 'system'
  | 'plugins'
  | 'experimental'

export interface OpenSettingsDetail {
  section?: SettingsSection
  blueprintId?: string
  teamId?: string
  definitionKind?: DefinitionKind
  definitionId?: string
  /** Open the Remotes pane already on the add form (zero-remotes bind path). */
  addRemote?: boolean
  /** #494: open Remotes focused on this remote instance (auth-gap remedy). */
  remoteId?: string
  /** REQ-88: jump to that provider's rate-limit fields. */
  providerId?: string
  focusRateLimits?: boolean
  /**
   * #1703: open the CLI agents pane on the add form, already filled for this
   * detected CLI. Set by the host-CLI tip's "Add provider".
   */
  addCliName?: string
}

export function openSettingsSheet(detail?: OpenSettingsDetail): void {
  window.dispatchEvent(new CustomEvent<OpenSettingsDetail>(OPEN_SETTINGS_EVENT, { detail }))
}

export const SETTINGS_SECTIONS: readonly SettingsSection[] = [
  'general',
  'aesthetics',
  'providers',
  'definition',
  'blueprint',
  'remotes',
  'retention',
  'hostname',
  'about-me',
  'llm-profiles',
  'mcp',
  'cli-agents',
  'roles',
  'sandboxes',
  'backend-audit',
  'seat-doctor',
  'operator-activity',
  'rail',
  'image-gen',
  'speech',
  'system',
  'plugins',
  'experimental',
]

export const SETTINGS_SEARCH_CONTENT: Record<SettingsSection, string[]> = {
  general: [
    'theme', 'dark', 'light', 'streaming', 'notifications', 'toast', 'auto-expire', 'expire',
    'Show theme control in top bar',
  ],
  aesthetics: [
    'bubble', 'theme', 'bubbles', 'labels', 'buttons', 'visuals', 'style', 'appearance',
    'Bubble theme', 'Action-row button labels', 'mobile', 'tablet', 'desktop', 'viewport', 'responsive',
  ],
  providers: [
    'providers', 'provider', 'overview', 'backend', 'api profiles', 'cli runtimes',
    'system1', 'categorizer', 'gate', 'filter-in', 'filter-out',
  ],
  definition: ['definition', 'explain', 'instructions', 'prompt'],
  blueprint: ['blueprints', 'recipes', 'python', 'custom'],
  remotes: [
    'remote', 'hermes', 'omb', 'rakazo', 'herdr', 'trueforge', 'ssh',
    'Add a remote', 'Add remote', 'available remote kinds', 'Remote ID',
    'Herdr location', 'SSH host', 'SSH user', 'SSH identity env', 'Use SSH agent',
    'API key env', 'Test connection', 'Remove', 'nested open-swarm',
  ],
  retention: [
    'retention', 'chat', 'trash', 'persistence', 'archive',
    'Active Chats', 'Active threads', 'Conversations', 'Messages', 'In Trash',
    'Disk Used', 'Auto-compress at', 'Compress', 'Cull fraction', 'Cull trigger',
    'Strategy',
  ],
  hostname: [
    'network', 'ip', 'domain', 'host', 'override',
    'Location', 'Use system',
  ],
  'about-me': [
    'about me', 'about', 'operator', 'profile', 'name', 'timezone', 'notes',
    'What should agents know about you', 'Display name', 'Timezone',
  ],
  'llm-profiles': [
    'llm', 'models', 'litellm', 'profiles', 'default', 'task',
    'Override per task', 'Task class map', 'orchestration', 'auxiliary', 'delegation',
    'Add LLM profile', 'Advanced', 'Rate limits', 'What can be overridden per task',
    // #1745 — System1 is a model type in this pane, not a hidden custom URL.
    'system1', 'model type', 'categorizer', 'chat llm', 'gate', 'System1 categorizers',
    'SYSTEM1_BASE_URL', 'SYSTEM1_API_KEY',
  ],
  mcp: [
    'mcp', 'mcpServers', 'tools', 'modelcontextprotocol',
    'Configured MCP servers', 'Command', 'Args (comma-separated)',
    'Secret env name (optional)',
  ],
  'cli-agents': [
    'cli', 'claude', 'grok', 'gemini', 'codex', 'agy', 'custom', 'wrapper',
    'Command (space or quotes separated)', 'Hop context mode',
  ],
  roles: ['roles', 'safety', 'router', 'gate', 'skeptic', 'Delete custom role'],
  sandboxes: [
    'sandbox', 'docker', 'daytona', 'bare metal',
    'Sandbox provider',
  ],
  'backend-audit': [
    'audit', 'backend', 'activity', 'log', 'diagnostics',
    'Backend audit', 'Clear log', 'No sends recorded yet',
  ],
  'seat-doctor': [
    'doctor', 'seat doctor', 'diagnose', 'diagnosis', 'broken', 'unverified', 'ok',
    'quota', 'credit', 'auth', 'api key', 'not installed', 'not configured',
    'remediation', 'fix', 'Run diagnosis', 'deep', 'bucket', 'audit seats',
  ],
  'operator-activity': [
    'activity', 'audit', 'operator', 'visibility', 'log',
    'Operator activity', 'Operators only', 'Activity log is off',
  ],
  rail: ['avatar', 'order', 'bump', 'Bump completed agents to top', 'Bump scope'],
  'image-gen': ['image', 'images', 'generation', 'diffusion'],
  speech: ['speech', 'tts', 'stt', 'audio', 'voice', 'read-aloud', 'read aloud'],
  system: ['system', 'sqlite', 'database', 'facts', 'config', 'Config coverage', 'env-only', 'secrets', 'About & diagnostics', 'generations', 'diagnostics', 'raw model context', 'tool calls'],
  plugins: ['plugins', 'openapi', 'marketplace', 'tools', 'connectors', 'pack', 'import', 'plugin ids'],
  experimental: [
    'experimental', 'flags', 'toggles', 'mvp', 'bleeding edge',
    'OpenAI Agents SDK', 'openai-agents', 'OpenMousBot', 'Daytona', 'Daytona sandboxes',
    '3D robot canvas', 'robot3d', 'Computer control', 'computer_routines',
    'AI prompt rewrite', 'prompt_rewrite', 'Command palette',
  ],
}

export function isSettingsSection(value: string): value is SettingsSection {
  return (SETTINGS_SECTIONS as readonly string[]).includes(value)
}

export function settingsDetailFromQuery(
  raw: string | null | undefined,
): OpenSettingsDetail | null {
  if (raw == null) return null
  const trimmed = raw.trim()
  if (!trimmed) return null
  if (trimmed === 'true' || trimmed === '1') return {}
  if (isSettingsSection(trimmed)) return { section: trimmed }
  return {}
}

export interface SettingsSheetProps {
  isOpen: boolean
  onClose: () => void
  blueprintId?: string | null
  teamId?: string | null
  initialSection?: SettingsSection | null
  definitionKind?: DefinitionKind | null
  definitionId?: string | null
  initialAddRemote?: boolean
  initialProviderId?: string | null
  focusRateLimits?: boolean
  /** #494: remote instance to focus when opening on the Remotes section. */
  initialRemoteId?: string | null
  /** #1703: detected CLI to prefill the CLI-agents add form with. */
  initialAddCliName?: string | null
}
