/** User-facing remote kind labels. Kind id `omb` stays; never show "OMB". */
export const OPENMOUSBOT_LABEL = 'OpenMousBot'

export const REMOTE_KIND_LABELS: Record<string, string> = {
  hermes: 'Hermes',
  anythingllm: 'AnythingLLM',
  letta: 'Letta',
  openwebui: 'Open WebUI',
  flowise: 'Flowise',
  omb: OPENMOUSBOT_LABEL,
  rakazo: 'Rakazo',
  herdr: 'Herdr',
  swarm: 'Swarm',
  'open-swarm': 'open-swarm',
}

export function remoteKindLabel(id: string, fallback?: string): string {
  const key = (id || '').trim().toLowerCase()
  if (key === 'openmousbot' || key === 'openmausbot' || key === 'openmous') {
    return OPENMOUSBOT_LABEL
  }
  return REMOTE_KIND_LABELS[key] || fallback || OPENMOUSBOT_LABEL
}

export function isOpenMousBotKind(id: string): boolean {
  const key = (id || '').trim().toLowerCase()
  return key === 'omb' || key === 'openmousbot' || key === 'openmausbot' || key === 'openmous'
}
