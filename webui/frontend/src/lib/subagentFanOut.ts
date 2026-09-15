/**
 * Subagent Fan-Out types and parsers
 */

export const SUBAGENT_FAN_OUT_TYPE = 'subagent_fan_out' as const

export interface SubagentTaskInfo {
  id: string
  name: string
  parentAgentId?: string
  role?: string
  status?: 'running' | 'completed' | 'failed' | 'idle' | string
  summary?: string
  task?: string
  avatar_path?: string
}

export interface InterAgentTurn {
  id?: string
  from: string
  to: string
  content: string
  timestamp?: string | number
  role?: string
}

export interface InterAgentCommGroup {
  id?: string
  from: string
  to: string
  label?: string
  messages: InterAgentTurn[]
  summary?: string
}

export interface SubagentFanOutData {
  type?: typeof SUBAGENT_FAN_OUT_TYPE | 'teammate_task' | string
  title?: string
  summary?: string
  subagents: SubagentTaskInfo[]
  communications?: InterAgentCommGroup[]
  comms?: InterAgentCommGroup[]
  turns?: InterAgentTurn[]
}

function unwrapPayload(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const obj = value as Record<string, unknown>
  for (const key of ['result', 'data', 'event', 'payload', 'task']) {
    const nested = obj[key]
    if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
      const inner = nested as Record<string, unknown>
      if (
        String(inner.type || '').trim() === SUBAGENT_FAN_OUT_TYPE ||
        Array.isArray(inner.subagents) ||
        Array.isArray(inner.communications)
      ) {
        return inner
      }
    }
  }
  return obj
}

export function parseSubagentFanOut(value: unknown): SubagentFanOutData | null {
  let raw: unknown = value
  if (typeof raw === 'string') {
    const text = raw.trim()
    if (!text.startsWith('{')) return null
    try {
      raw = JSON.parse(text) as unknown
    } catch {
      return null
    }
  }
  const obj = unwrapPayload(raw)
  if (!obj) return null

  const type = String(obj.type || '').trim()
  const rawSubagents = obj.subagents
  const rawComms = obj.communications ?? obj.comms ?? obj.inter_agent_comms

  const isFanOutType = type === SUBAGENT_FAN_OUT_TYPE
  const isTeammateWithSubagents =
    type === 'teammate_task' && Array.isArray(rawSubagents) && rawSubagents.length > 0
  const hasSubagentsArray = Array.isArray(rawSubagents) && rawSubagents.length > 0

  if (!isFanOutType && !isTeammateWithSubagents && !hasSubagentsArray) {
    return null
  }

  const subagents: SubagentTaskInfo[] = []
  if (Array.isArray(rawSubagents)) {
    for (const item of rawSubagents) {
      if (item && typeof item === 'object') {
        const id = String(item.id || item.agentId || item.name || '').trim()
        if (!id) continue
        const name = String(item.name || item.id || '').trim() || id
        const role = item.role ? String(item.role).trim() : undefined
        const status = item.status ? String(item.status).trim() : 'running'
        const summary = item.summary
          ? String(item.summary).trim()
          : item.task
            ? String(item.task).trim()
            : undefined
        const task = item.task ? String(item.task).trim() : undefined
        const parentAgentId =
          item.parentAgentId || item.parent_agent_id
            ? String(item.parentAgentId || item.parent_agent_id).trim()
            : undefined
        const avatar_path = item.avatar_path ? String(item.avatar_path).trim() : undefined
        subagents.push({
          id,
          name,
          role,
          status,
          summary,
          task,
          parentAgentId,
          avatar_path,
        })
      }
    }
  }

  const communications: InterAgentCommGroup[] = []
  if (Array.isArray(rawComms)) {
    for (let i = 0; i < rawComms.length; i++) {
      const comm = rawComms[i]
      if (comm && typeof comm === 'object') {
        const from = String(comm.from || comm.sender || '').trim()
        const to = String(comm.to || comm.receiver || comm.recipient || '').trim()
        const label = comm.label
          ? String(comm.label).trim()
          : from && to
            ? `${from} → ${to}`
            : undefined
        const rawMsgs = comm.messages ?? comm.turns ?? []
        const messages: InterAgentTurn[] = []
        if (Array.isArray(rawMsgs)) {
          for (const msg of rawMsgs) {
            if (msg && typeof msg === 'object') {
              messages.push({
                id: msg.id ? String(msg.id) : undefined,
                from: String(msg.from || msg.sender || from).trim(),
                to: String(msg.to || msg.receiver || to).trim(),
                content: String(msg.content || msg.text || msg.message || '').trim(),
                timestamp: msg.timestamp,
                role: msg.role ? String(msg.role) : undefined,
              })
            }
          }
        }
        communications.push({
          id: String(comm.id || `comm-${i}-${from}-${to}`),
          from: from || 'Agent',
          to: to || 'Agent',
          label,
          messages,
          summary: comm.summary ? String(comm.summary) : undefined,
        })
      }
    }
  }

  const turns: InterAgentTurn[] = []
  if (Array.isArray(obj.turns)) {
    for (const msg of obj.turns) {
      if (msg && typeof msg === 'object') {
        turns.push({
          id: msg.id ? String(msg.id) : undefined,
          from: String(msg.from || msg.sender || '').trim(),
          to: String(msg.to || msg.receiver || '').trim(),
          content: String(msg.content || msg.text || msg.message || '').trim(),
          timestamp: msg.timestamp,
          role: msg.role ? String(msg.role) : undefined,
        })
      }
    }
  }

  if (communications.length === 0 && turns.length > 0) {
    const grouped = new Map<string, InterAgentTurn[]>()
    for (const turn of turns) {
      const key = `${turn.from} → ${turn.to}`
      if (!grouped.has(key)) grouped.set(key, [])
      grouped.get(key)!.push(turn)
    }
    let idx = 0
    for (const [label, msgs] of grouped.entries()) {
      const [from, to] = label.split(' → ')
      communications.push({
        id: `comm-turn-${idx++}`,
        from: from || 'Agent',
        to: to || 'Agent',
        label,
        messages: msgs,
      })
    }
  }

  const title = obj.title ? String(obj.title).trim() : undefined
  const summary = obj.summary ? String(obj.summary).trim() : undefined

  return {
    type: SUBAGENT_FAN_OUT_TYPE,
    title,
    summary,
    subagents,
    communications,
    turns,
  }
}
