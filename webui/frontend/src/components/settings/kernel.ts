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
  | 'llm-profiles'
  | 'mcp'
  | 'cli-agents'
  | 'roles'
  | 'sandboxes'
  | 'backend-audit'
  | 'rail'
  | 'image-gen'
  | 'speech'
  | 'system'
  | 'plugins'

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
}

export function openSettingsSheet(detail?: OpenSettingsDetail): void {
  window.dispatchEvent(new CustomEvent<OpenSettingsDetail>(OPEN_SETTINGS_EVENT, { detail }))
}

export const SETTINGS_SECTIONS: readonly SettingsSection[] = [
  'general',
  'aesthetics',
  'definition',
  'blueprint',
  'remotes',
  'retention',
  'hostname',
  'llm-profiles',
  'mcp',
  'cli-agents',
  'roles',
  'sandboxes',
  'backend-audit',
  'rail',
  'image-gen',
  'speech',
  'system',
  'plugins',
]

export const SETTINGS_SEARCH_CONTENT: Record<SettingsSection, string[]> = {
  general: [
    'theme', 'dark', 'light', 'streaming', 'notifications', 'toast', 'auto-expire', 'expire',
    'Show theme control in top bar',
  ],
  aesthetics: [
    'bubble', 'theme', 'bubbles', 'labels', 'buttons', 'visuals', 'style', 'appearance',
    'Bubble theme', 'Action-row button labels',
  ],
  providers: ['providers', 'provider', 'overview', 'backend', 'api profiles', 'cli runtimes'],
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
  'llm-profiles': [
    'llm', 'models', 'litellm', 'profiles', 'default', 'task',
    'Override per task', 'Task class map', 'orchestration', 'auxiliary', 'delegation',
    'Add LLM profile', 'Advanced', 'Rate limits', 'What can be overridden per task',
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
  rail: ['avatar', 'order', 'bump', 'Bump completed agents to top', 'Bump scope'],
  'image-gen': ['image', 'images', 'generation', 'diffusion'],
  speech: ['speech', 'tts', 'stt', 'audio', 'voice', 'read-aloud', 'read aloud'],
  system: ['system', 'sqlite', 'database', 'facts', 'config', 'Config coverage', 'env-only', 'secrets'],
  plugins: ['plugins', 'openapi', 'marketplace', 'tools', 'connectors'],
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
}
