import { useEffect, useMemo, useState, type KeyboardEvent } from 'react'
import {
  Users,
  CheckCircle2,
  Clock,
  AlertCircle,
  MessageSquare,
  ChevronDown,
  ChevronUp,
  ArrowRight,
  Sparkles,
} from 'lucide-react'
import AgentAvatar from './AgentAvatar'
import { registerDynamicSubagent } from '../lib/dynamicSubagents'
import {
  parseSubagentFanOut,
  type InterAgentCommGroup,
  type InterAgentTurn,
  type SubagentFanOutData,
  type SubagentTaskInfo,
} from '../lib/subagentFanOut'

export interface SubagentFanOutBlockProps {
  event?: SubagentFanOutData | Record<string, unknown>
  subagents?: SubagentTaskInfo[]
  communications?: InterAgentCommGroup[]
  comms?: InterAgentCommGroup[]
  title?: string
  summary?: string
  className?: string
  onSelectAgent?: (agentId: string) => void
}

function normalizeStatus(status?: string): 'completed' | 'running' | 'failed' | 'idle' {
  const s = (status || '').trim().toLowerCase()
  if (s === 'completed' || s === 'done' || s === 'finished' || s === 'success') return 'completed'
  if (s === 'running' || s === 'in_progress' || s === 'working' || s === 'active') return 'running'
  if (s === 'failed' || s === 'error' || s === 'denied' || s === 'rejected') return 'failed'
  return 'idle'
}

function statusBadgeClass(status: string) {
  const normalized = normalizeStatus(status)
  switch (normalized) {
    case 'completed':
      return 'badge-success text-success-content bg-success/20 border-success/30'
    case 'running':
      return 'badge-info text-info-content bg-info/20 border-info/30'
    case 'failed':
      return 'badge-error text-error-content bg-error/20 border-error/30'
    default:
      return 'badge-ghost text-base-content/70'
  }
}

function StatusIcon({ status }: { status: string }) {
  const normalized = normalizeStatus(status)
  switch (normalized) {
    case 'completed':
      return <CheckCircle2 className="w-3.5 h-3.5 text-success" />
    case 'running':
      return <Clock className="w-3.5 h-3.5 text-info animate-spin" />
    case 'failed':
      return <AlertCircle className="w-3.5 h-3.5 text-error" />
    default:
      return <Clock className="w-3.5 h-3.5 opacity-50" />
  }
}

export default function SubagentFanOutBlock({
  event,
  subagents: directSubagents,
  communications: directComms,
  comms: alternateComms,
  title: directTitle,
  summary: directSummary,
  className = '',
  onSelectAgent,
}: SubagentFanOutBlockProps) {
  const parsedEvent = useMemo(() => {
    if (!event) return null
    return parseSubagentFanOut(event) ?? (event as unknown as SubagentFanOutData)
  }, [event])

  const subagents = useMemo<SubagentTaskInfo[]>(() => {
    if (directSubagents && directSubagents.length > 0) return directSubagents
    if (parsedEvent?.subagents && parsedEvent.subagents.length > 0) return parsedEvent.subagents
    return []
  }, [directSubagents, parsedEvent])

  const communications = useMemo<InterAgentCommGroup[]>(() => {
    if (directComms && directComms.length > 0) return directComms
    if (alternateComms && alternateComms.length > 0) return alternateComms
    if (parsedEvent?.communications && parsedEvent.communications.length > 0) {
      return parsedEvent.communications
    }
    if (parsedEvent?.comms && parsedEvent.comms.length > 0) {
      return parsedEvent.comms
    }
    // Fallback from flat turns if present
    if (Array.isArray(parsedEvent?.turns) && parsedEvent.turns.length > 0) {
      const grouped = new Map<string, InterAgentTurn[]>()
      for (const turn of parsedEvent.turns) {
        const key = `${turn.from} → ${turn.to}`
        if (!grouped.has(key)) grouped.set(key, [])
        grouped.get(key)!.push(turn)
      }
      return Array.from(grouped.entries()).map(([label, msgs], i) => {
        const [from, to] = label.split(' → ')
        return {
          id: `comm-turn-${i}`,
          from: from || 'Agent A',
          to: to || 'Agent B',
          label,
          messages: msgs,
        }
      })
    }
    return []
  }, [directComms, alternateComms, parsedEvent])

  // Register dynamic subagents automatically when component mounts/receives them
  useEffect(() => {
    for (const subagent of subagents) {
      if (subagent.id) {
        registerDynamicSubagent({
          id: subagent.id,
          name: subagent.name || subagent.id,
          parentAgentId: subagent.parentAgentId,
          role: subagent.role,
          status: subagent.status || 'running',
          summary: subagent.summary || subagent.task,
          task: subagent.task,
          avatar_path: subagent.avatar_path,
        })
      }
    }
  }, [subagents])

  const [expandedCommIds, setExpandedCommIds] = useState<Set<string>>(new Set())

  const toggleComm = (id: string) => {
    setExpandedCommIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleCommKeyDown = (event: KeyboardEvent, id: string) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      toggleComm(id)
    }
  }

  const headerTitle = useMemo(() => {
    if (directTitle) return directTitle
    if (directSummary) return directSummary
    if (parsedEvent?.title) return parsedEvent.title
    if (parsedEvent?.summary) return parsedEvent.summary
    const count = subagents.length
    return count === 1 ? '1 Subagent Fanned Out' : `${count} Subagents Fanned Out`
  }, [directTitle, directSummary, parsedEvent, subagents.length])

  const completedCount = subagents.filter(
    (s) => normalizeStatus(s.status) === 'completed',
  ).length
  const runningCount = subagents.filter((s) => normalizeStatus(s.status) === 'running').length

  return (
    <div
      className={`os-subagent-fan-out-block card border border-base-300/70 bg-base-200/40 backdrop-blur-sm shadow-sm rounded-xl p-3.5 my-2.5 transition-all text-sm w-full max-w-2xl ${className}`}
      data-testid="subagent-fan-out-block"
      role="region"
      aria-label={headerTitle}
    >
      {/* Header */}
      <div
        className="os-fan-out-header flex items-center justify-between gap-2 pb-2.5 border-b border-base-300/60"
        data-testid="fan-out-header"
      >
        <div className="flex items-center gap-2 font-semibold text-base-content tracking-tight">
          <div className="w-6 h-6 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
            <Users className="w-3.5 h-3.5" />
          </div>
          <span data-testid="fan-out-title">{headerTitle}</span>
        </div>

        <div className="flex items-center gap-1.5">
          {completedCount > 0 && (
            <span className="badge badge-success badge-sm gap-1 py-1 px-2 font-medium">
              <CheckCircle2 className="w-3 h-3" />
              {completedCount} done
            </span>
          )}
          {runningCount > 0 && (
            <span className="badge badge-info badge-sm gap-1 py-1 px-2 font-medium">
              <Clock className="w-3 h-3 animate-spin" />
              {runningCount} active
            </span>
          )}
        </div>
      </div>

      {/* Subagent list */}
      <div className="os-subagent-list mt-3 space-y-2" data-testid="subagent-list">
        {subagents.map((subagent) => {
          const status = subagent.status || 'running'
          const summaryText = subagent.summary || subagent.task || 'Task in progress...'
          return (
            <div
              key={subagent.id}
              className="os-subagent-item flex flex-col gap-1 rounded-lg bg-base-100/70 border border-base-300/50 p-2.5 hover:bg-base-100 transition-colors"
              data-testid="subagent-item"
              data-subagent-id={subagent.id}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="shrink-0">
                    <AgentAvatar
                      agentId={subagent.id}
                      src={subagent.avatar_path}
                      size="xs"
                      status={normalizeStatus(status) === 'running' ? 'working' : 'idle'}
                      active={normalizeStatus(status) === 'running'}
                    />
                  </div>
                  <span
                    className="font-medium text-base-content truncate cursor-pointer hover:underline"
                    data-testid="subagent-name"
                    onClick={() => onSelectAgent?.(subagent.id)}
                  >
                    {subagent.name}
                  </span>
                  {subagent.role && (
                    <span
                      className="badge badge-ghost badge-xs text-[10px] uppercase font-mono px-1.5 py-0.5 opacity-80"
                      data-testid="subagent-role"
                    >
                      {subagent.role}
                    </span>
                  )}
                </div>

                <div
                  className={`badge badge-sm gap-1 border font-medium ${statusBadgeClass(status)}`}
                  data-testid="subagent-status"
                >
                  <StatusIcon status={status} />
                  <span>{status}</span>
                </div>
              </div>

              {summaryText && (
                <div
                  className="os-subagent-summary text-xs text-base-content/75 pl-8 pr-1 mt-0.5 leading-relaxed"
                  data-testid="subagent-summary"
                >
                  {summaryText}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Inter-Agent Communications section */}
      {communications.length > 0 && (
        <div className="os-inter-agent-comms mt-3.5 pt-3 border-t border-base-300/60">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-base-content/70 mb-2 uppercase tracking-wider">
            <MessageSquare className="w-3.5 h-3.5 text-primary/80" />
            <span>Inter-Agent Comms</span>
          </div>

          {/* Clickable communication pills */}
          <div className="flex flex-wrap gap-2" role="group" aria-label="Inter-Agent Communication Channels">
            {communications.map((comm) => {
              const commId = comm.id || `${comm.from}-${comm.to}`
              const isExpanded = expandedCommIds.has(commId)
              const label = comm.label || `${comm.from} → ${comm.to}`
              const count = comm.messages?.length ?? 0

              return (
                <button
                  key={commId}
                  type="button"
                  onClick={() => toggleComm(commId)}
                  onKeyDown={(e) => handleCommKeyDown(e, commId)}
                  className={`btn btn-xs gap-1.5 rounded-full font-normal border transition-all ${
                    isExpanded
                      ? 'btn-primary text-primary-content shadow-sm'
                      : 'btn-outline border-base-300 hover:border-primary hover:bg-primary/5 text-base-content/90'
                  }`}
                  data-testid="inter-agent-comm-pill"
                  data-comm-id={commId}
                  aria-expanded={isExpanded}
                  aria-label={`Toggle communications between ${comm.from} and ${comm.to}`}
                >
                  <MessageSquare className="w-3 h-3" />
                  <span className="font-medium">{label}</span>
                  {count > 0 && (
                    <span
                      className={`badge badge-xs px-1 ${
                        isExpanded ? 'bg-primary-content text-primary' : 'badge-ghost'
                      }`}
                      data-testid="comm-pill-count"
                    >
                      {count}
                    </span>
                  )}
                  {isExpanded ? (
                    <ChevronUp className="w-3 h-3 ml-0.5 opacity-70" />
                  ) : (
                    <ChevronDown className="w-3 h-3 ml-0.5 opacity-70" />
                  )}
                </button>
              )
            })}
          </div>

          {/* Expanded comms transcript panels */}
          <div className="space-y-2.5 mt-2.5">
            {communications
              .filter((comm) => expandedCommIds.has(comm.id || `${comm.from}-${comm.to}`))
              .map((comm) => {
                const commId = comm.id || `${comm.from}-${comm.to}`
                const label = comm.label || `${comm.from} → ${comm.to}`
                const messages = comm.messages ?? []

                return (
                  <div
                    key={commId}
                    className="os-inter-agent-transcript rounded-xl border border-base-300 bg-base-100 p-3 shadow-inner"
                    data-testid="inter-agent-transcript"
                    data-comm-id={commId}
                  >
                    <div className="flex items-center justify-between pb-2 mb-2 border-b border-base-200 text-xs text-base-content/70">
                      <span className="font-semibold text-base-content flex items-center gap-1">
                        <Sparkles className="w-3 h-3 text-primary" />
                        Transcript: {label}
                      </span>
                      <span>{messages.length} turns</span>
                    </div>

                    {messages.length === 0 ? (
                      <p className="text-xs text-base-content/50 italic py-1">
                        No direct messages recorded.
                      </p>
                    ) : (
                      <div className="space-y-2">
                        {messages.map((msg, index) => {
                          const isSenderFrom = msg.from.toLowerCase() === comm.from.toLowerCase()
                          return (
                            <div
                              key={msg.id || `msg-${index}`}
                              className={`p-2.5 rounded-lg text-xs ${
                                isSenderFrom
                                  ? 'bg-base-200/90 border border-base-300/70 ml-0 mr-4'
                                  : 'bg-primary/5 border border-primary/20 ml-4 mr-0'
                              }`}
                              data-testid="inter-agent-message"
                            >
                              <div className="flex items-center justify-between text-[11px] font-semibold text-base-content/80 mb-1">
                                <span className="flex items-center gap-1 text-primary">
                                  <span>{msg.from}</span>
                                  <ArrowRight className="w-2.5 h-2.5 opacity-60" />
                                  <span>{msg.to}</span>
                                </span>
                                {msg.timestamp && (
                                  <span className="text-base-content/40 font-normal">
                                    {String(msg.timestamp)}
                                  </span>
                                )}
                              </div>
                              <div className="whitespace-pre-wrap text-base-content leading-relaxed">
                                {msg.content}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })}
          </div>
        </div>
      )}
    </div>
  )
}
