/**
 * Rail attention when an agent is blocked on Safety approval (#446).
 *
 * ChatPage publishes; AgentSidebar paints orange on the pin and snippet line.
 */

export const AGENT_ATTENTION_EVENT = 'swarm:agent-attention'
export const NEEDS_APPROVAL_LABEL = 'Needs approval'

const pending = new Map<string, Set<string>>()

export function resetAgentAttention(): void {
  pending.clear()
}

export function peekApprovalWait(agentId: string): boolean {
  return Boolean(agentId) && (pending.get(agentId)?.size ?? 0) > 0
}

export function notifyApprovalWait(agentId: string, toolId: string, waiting: boolean): void {
  if (!agentId || !toolId) return
  let tools = pending.get(agentId)
  if (!tools) {
    tools = new Set()
    pending.set(agentId, tools)
  }
  if (waiting) tools.add(toolId)
  else tools.delete(toolId)
  if (tools.size === 0) pending.delete(agentId)
  try {
    window.dispatchEvent(
      new CustomEvent(AGENT_ATTENTION_EVENT, {
        detail: { agentId, waiting: pending.has(agentId) },
      }),
    )
  } catch {
    /* window unavailable */
  }
}

export function approvalWaitFromEvent(
  event: Event,
): { agentId: string; waiting: boolean } | null {
  const detail = (event as CustomEvent<{ agentId?: unknown; waiting?: unknown }>).detail
  if (typeof detail?.agentId !== 'string' || !detail.agentId) return null
  return { agentId: detail.agentId, waiting: Boolean(detail.waiting) }
}
