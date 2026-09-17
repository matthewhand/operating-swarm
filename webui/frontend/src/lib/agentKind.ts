/** Classify chat agents as API, CLI, remote, or blueprint (REQ-49 / REQ-203).
 *
 * Blueprint agents are swarm-owned threads like API agents (editable in
 * place). CLI and remote sessions are owned outside swarm.
 */

export type AgentKind = 'api' | 'cli' | 'remote' | 'blueprint'

const KINDS = new Set<AgentKind>(['api', 'cli', 'remote', 'blueprint'])

/** Remote implementations — not an extra user-facing kind (ADR-011). */
const REMOTE_IMPL_IDS = new Set([
  'herdr',
  'hermes',
  'anythingllm',
  'letta',
  'memgpt',
  'openwebui',
  'open-webui',
  'open_webui',
  'owui',
  'flowise',
  'flowiseai',
  'n8n',
  'n8n-io',
  'omb',
  'rakazo',
  'openmausbot',
  'openmaus',
  'openmousbot',
  'rakoza',
  'open-swarm',
  'openswarm',
  'open_swarm',
  'trueforge',
  'true_forge',
  'true-forge',
  'slack',
  'slackbot',
  'slack-api',
  'slack_api',
  'nemo-slack',
  'nemo_slack',
])

export function isRemoteImplId(raw: string | null | undefined): boolean {
  const key = (raw ?? '').trim().toLowerCase()
  if (!key) return false
  if (key.startsWith('herdr:') || key.startsWith('remote:')) return true
  return REMOTE_IMPL_IDS.has(key)
}

export function classifyAgentKind(
  raw: string | null | undefined,
  explicit?: string | null,
): AgentKind {
  if (explicit && KINDS.has(explicit as AgentKind)) {
    return explicit as AgentKind
  }
  if (isRemoteImplId(explicit)) return 'remote'
  const text = (raw ?? '').trim().toLowerCase()
  if (text.startsWith('cli:')) return 'cli'
  if (text.startsWith('blueprint:')) return 'blueprint'
  if (
    text.startsWith('remote:') ||
    text.startsWith('placeholder:remote:') ||
    text.startsWith('herdr:') ||
    isRemoteImplId(text)
  ) {
    return 'remote'
  }
  return 'api'
}

/** True for swarm-owned threads (API + blueprint). CLI/remote sessions are owned outside swarm. */
export function isSwarmOwnedAgent(
  raw: string | null | undefined,
  explicit?: string | null,
): boolean {
  const kind = classifyAgentKind(raw, explicit)
  return kind === 'api' || kind === 'blueprint'
}

/** True for editable threads: API + blueprint + CLI (edit restarts the
 * provider session — REQ-808). Remote threads stay read-only (REQ-49). */
export function canEditAgentMessages(
  raw: string | null | undefined,
  explicit?: string | null,
): boolean {
  return classifyAgentKind(raw, explicit) !== 'remote'
}
