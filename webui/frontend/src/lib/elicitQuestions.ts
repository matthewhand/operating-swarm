/** Per-seat opt-in for agent-initiated questions (#221). Default off. */

const STORAGE_PREFIX = 'swarm_elicit_questions:'

export function elicitQuestionsStorageKey(agentId: string): string {
  return `${STORAGE_PREFIX}${agentId}`
}

export function loadElicitQuestions(agentId: string): boolean {
  if (!agentId) return false
  try {
    return window.localStorage.getItem(elicitQuestionsStorageKey(agentId)) === 'true'
  } catch {
    return false
  }
}

export function saveElicitQuestions(agentId: string, value: boolean): void {
  if (!agentId) return
  try {
    const key = elicitQuestionsStorageKey(agentId)
    if (value) window.localStorage.setItem(key, 'true')
    else window.localStorage.removeItem(key)
  } catch {
    // quota / private mode — stay default-off
  }
}
