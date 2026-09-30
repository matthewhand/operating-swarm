/** User-facing remote kind labels. Kind id `omb` stays; never show "OMB". */
export const OPENMOUSBOT_LABEL = 'OpenMousBot'

/**
 * OpenMuse is a *different* product from OpenMousBot (`omb`). The two share a
 * name prefix and nothing else: OpenMuse is the Hono agent server whose
 * sessions are tasks, so it gets its own label and its own kind id.
 */
export const OPENMUSE_LABEL = 'OpenMuse'

export const REMOTE_KIND_LABELS: Record<string, string> = {
  hermes: 'Hermes',
  anythingllm: 'AnythingLLM',
  openwebui: 'Open WebUI',
  flowise: 'Flowise',
  n8n: 'n8n',
  omb: OPENMOUSBOT_LABEL,
  rakazo: 'Rakazo',
  herdr: 'Herdr',
  swarm: 'Swarm',
  'open-swarm': 'open-swarm',
  trueforge: 'TrueForge',
  openmuse: OPENMUSE_LABEL,
}

/** Spelling variants that share one kind label. ``open-swarm`` stays its own label. */
const KIND_ALIASES: Record<string, string> = {
  'anything-llm': 'anythingllm',
  anything_llm: 'anythingllm',
  'open-webui': 'openwebui',
  open_webui: 'openwebui',
  owui: 'openwebui',
  flowiseai: 'flowise',
  'n8n-io': 'n8n',
  openmaus: 'omb',
  openswarm: 'open-swarm',
  open_swarm: 'open-swarm',
  rakoza: 'rakazo',
  true_forge: 'trueforge',
  'open-muse': 'openmuse',
  open_muse: 'openmuse',
  'true-forge': 'trueforge',
}

/** Kind label for a rail subtitle. Unknown kinds stay blank — never "Remote team". */
export function remoteKindRailLabel(id: string): string {
  const key = (id || '').trim().toLowerCase()
  if (!key) return ''
  if (key === 'openmousbot' || key === 'openmausbot' || key === 'openmous') {
    return OPENMOUSBOT_LABEL
  }
  return REMOTE_KIND_LABELS[key] || ''
}

/**
 * #1436 / #1441 — rail detail under a remote row.
 * A message snippet or description wins. Otherwise the implementation label
 * (Herdr, OpenMousBot, …) when it adds information the title does not already
 * show. Remotes are not teams, so there is no "Remote team" fallback.
 */
export function remoteRailDetail(
  remote: { kind?: string; title?: string; description?: string },
  snippet?: string,
): string {
  const snip = (snippet || '').trim()
  if (snip) return snip
  const description = (remote.description || '').trim()
  if (description) return description
  const label = remoteKindRailLabel(remote.kind || '')
  const title = (remote.title || '').trim()
  if (label && label.toLowerCase() !== title.toLowerCase()) return label
  return ''
}

export function remoteKindLabel(id: string, fallback?: string): string {
  const key = (id || '').trim().toLowerCase()
  if (!key) return fallback || ''
  if (isOpenMousBotKind(key)) return OPENMOUSBOT_LABEL
  const resolved = KIND_ALIASES[key] || key
  if (isOpenMousBotKind(resolved)) return OPENMOUSBOT_LABEL
  return REMOTE_KIND_LABELS[resolved] || fallback || resolved
}

export function isOpenMousBotKind(id: string): boolean {
  const key = (id || '').trim().toLowerCase()
  const resolved = KIND_ALIASES[key] || key
  return (
    resolved === 'omb' ||
    key === 'openmousbot' ||
    key === 'openmausbot' ||
    key === 'openmous'
  )
}

/** Quiet subtitle when a remote row has no conversation snippet.
 * A named instance shows its kind (TrueForge). A row already titled with
 * that kind shows the seat word Remote, so the name is not repeated.
 */
export function remoteQuietSubtitle(remote: {
  kind?: string
  id?: string
  title?: string
  description?: string
}): string {
  const description = (remote.description || '').trim()
  if (description) return description
  const kindLabel = remoteKindLabel(remote.kind || remote.id || '')
  const title = (remote.title || '').trim()
  if (kindLabel && kindLabel.toLowerCase() !== title.toLowerCase()) return kindLabel
  return 'Remote'
}
