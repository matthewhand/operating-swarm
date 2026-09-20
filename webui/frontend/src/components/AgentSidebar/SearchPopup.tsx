import { useEffect, useMemo, useRef, useState } from 'react'
import { Bot, MessageSquare, Network, Search, X } from 'lucide-react'
import type { Agent, ChatMessage, DelegationEvent } from '../../types/agent'
import {
  buildSearchHits,
  type SearchHit,
  type SearchScope,
} from '../../lib/agent-utils'

const SCOPES: { id: SearchScope; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'bots', label: 'Agents' },
  { id: 'messages', label: 'Messages' },
  { id: 'delegations', label: 'Delegations' },
]

const RECENT_KEY = 'agent_search_recent_ids'

function loadRecentIds(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    return raw ? (JSON.parse(raw) as string[]) : []
  } catch {
    return []
  }
}

function saveRecentId(agentId: string) {
  const next = [agentId, ...loadRecentIds().filter((id) => id !== agentId)].slice(0, 12)
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next))
  } catch {
    /* ignore */
  }
}

interface SearchPopupProps {
  agents: Agent[]
  messages?: ChatMessage[]
  delegations?: DelegationEvent[]
  query: string
  onQueryChange: (query: string) => void
  onClose: () => void
  onSelectAgent: (agentId: string) => void
  onSelectDelegation?: (id: string) => void
}

export function SearchPopup({
  agents,
  messages = [],
  delegations = [],
  query,
  onQueryChange,
  onClose,
  onSelectAgent,
  onSelectDelegation,
}: SearchPopupProps) {
  const [scope, setScope] = useState<SearchScope>('all')
  const inputRef = useRef<HTMLInputElement>(null)
  const recentIds = useMemo(() => loadRecentIds(), [])

  useEffect(() => {
    inputRef.current?.focus()
    inputRef.current?.select()
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const hits = useMemo(
    () =>
      buildSearchHits({
        agents,
        messages,
        delegations,
        query,
        scope,
        recentAgentIds: recentIds,
      }),
    [agents, messages, delegations, query, scope, recentIds],
  )

  const choose = (hit: SearchHit) => {
    if (hit.kind === 'delegation' && onSelectDelegation) {
      onSelectDelegation(hit.id.replace(/^del:/, ''))
    }
    if (hit.agentId) {
      saveRecentId(hit.agentId)
      onSelectAgent(hit.agentId)
    }
    onClose()
  }

  const empty = !query.trim()

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 p-4 pt-[12vh]"
      role="presentation"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search"
        className="w-full max-w-lg rounded-2xl border border-base-300 bg-base-100 shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-base-300 px-3 py-2">
          <Search className="w-4 h-4 text-base-content/40 shrink-0" aria-hidden />
          <input
            ref={inputRef}
            type="search"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="Search agents, messages…"
            className="input input-sm input-ghost flex-1 px-0 focus:outline-none"
            aria-label="Search query"
          />
          <button
            type="button"
            className="btn btn-ghost btn-xs btn-circle"
            aria-label="Close search"
            onClick={onClose}
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex gap-1 px-3 py-2 border-b border-base-300/80" role="tablist" aria-label="Search filters">
          {SCOPES.map((s) => (
            <button
              key={s.id}
              type="button"
              role="tab"
              aria-selected={scope === s.id}
              className={`btn btn-xs rounded-full ${
                scope === s.id ? 'btn-primary' : 'btn-ghost border border-base-300'
              }`}
              onClick={() => setScope(s.id)}
            >
              {s.label}
            </button>
          ))}
        </div>

        <div className="max-h-[50vh] overflow-y-auto py-1">
          {empty && (
            <p className="px-3 py-1.5 text-[11px] uppercase tracking-wider font-bold text-base-content/40">
              Previous
            </p>
          )}
          {hits.length === 0 ? (
            <p className="px-4 py-6 text-sm text-base-content/50 text-center">
              {empty ? 'Nothing recent yet — type to search everything.' : `No matches for “${query}”.`}
            </p>
          ) : (
            hits.map((hit) => (
              <button
                key={hit.id}
                type="button"
                className="w-full flex items-start gap-2.5 px-3 py-2 text-left hover:bg-base-200"
                onClick={() => choose(hit)}
              >
                <span className="mt-0.5 text-base-content/45">
                  {hit.kind === 'bot' ? (
                    <Bot className="w-4 h-4" aria-hidden />
                  ) : hit.kind === 'message' ? (
                    <MessageSquare className="w-4 h-4" aria-hidden />
                  ) : (
                    <Network className="w-4 h-4" aria-hidden />
                  )}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium truncate">{hit.title}</span>
                  <span className="block text-[11px] text-base-content/50 truncate">
                    {hit.kind === 'bot' ? 'Agent' : hit.kind === 'message' ? 'Message' : 'Delegation'}
                    {' · '}
                    {hit.subtitle}
                  </span>
                </span>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
