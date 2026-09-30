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
  'octop',
  'tencent-octop',
  'tencentoctop',
  'tencent_octop',
])

export function isRemoteImplId(raw: string | null | undefined): boolean {
  const key = (raw ?? '').trim().toLowerCase()
  if (!key) return false
  if (key.startsWith('herdr:') || key.startsWith('remote:')) return true
  return REMOTE_IMPL_IDS.has(key)
}

/** Drop a leading `blueprint:` persistence tag (#1436). */
export function peeledSeatId(raw: string | null | undefined): string {
  let text = (raw ?? '').trim()
  while (text.toLowerCase().startsWith('blueprint:')) {
    text = text.slice('blueprint:'.length)
  }
  return text
}

/** True when the id is a `cli:` seat, including `blueprint:cli:grok`. */
export function isCliPrefixedSeatId(raw: string | null | undefined): boolean {
  return peeledSeatId(raw).trim().toLowerCase().startsWith('cli:')
}

/** True when the id is a remote seat, including `blueprint:omb` and `blueprint:remote:herdr`. */
export function isRemoteSeatId(raw: string | null | undefined): boolean {
  const text = peeledSeatId(raw).trim().toLowerCase()
  if (!text) return false
  if (text === 'remote_harness') return true
  if (
    text.startsWith('remote:') ||
    text.startsWith('placeholder:remote:') ||
    text.startsWith('herdr:')
  ) {
    return true
  }
  return isRemoteImplId(text)
}

export function classifyAgentKind(
  raw: string | null | undefined,
  explicit?: string | null,
): AgentKind {
  const text = (raw ?? '').trim().toLowerCase()
  const explicitKind = (explicit ?? '').trim().toLowerCase()
  // #1436: a blueprint tag must not hide a remote or cli: seat. Explicit api still wins.
  if (explicitKind === 'blueprint' && isRemoteSeatId(text)) return 'remote'
  if (explicitKind === 'blueprint' && isCliPrefixedSeatId(text)) return 'cli'
  if (explicit && KINDS.has(explicit as AgentKind)) {
    return explicit as AgentKind
  }
  if (isRemoteImplId(explicit) || isRemoteSeatId(explicit)) return 'remote'
  if (isRemoteSeatId(text)) return 'remote'
  if (text.startsWith('cli:') || isCliPrefixedSeatId(text)) return 'cli'
  // #534: `cli_agent` is the CLI-fleet recipe. Remote recipes are covered by
  // isRemoteSeatId (including `blueprint:remote_harness`).
  if (text === 'cli_agent') return 'cli'
  if (text.startsWith('blueprint:')) return 'blueprint'
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
