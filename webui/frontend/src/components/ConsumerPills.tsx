import { useEffect, useState } from 'react'
import { fetchAgentSuggestions } from '../lib/suggestions'
import {
  ROLE_CONSUMERS_CHANGED_EVENT,
  loadProviderEdges,
  type RoleConsumerEdge,
} from '../lib/roleConsumers'
import { loadAgentEdit } from '../lib/agentEdits'

/**
 * #532 / REQ-919 — consumer pills on a role provider's chat.
 *
 * Browsing the seat that *provides* a role (e.g. Charles, suggestions) shows
 * a pill per agent wired to consult it. Clicking a pill expands the
 * interactions exchanged with that consumer — at minimum the suggestions the
 * provider would hand it right now, fetched live from the public endpoint
 * (honest: nothing cached, nothing invented).
 */

function consumerLabel(consumerId: string): string {
  const edit = loadAgentEdit(consumerId)
  return edit.name || consumerId
}

function edgeKey(edge: RoleConsumerEdge): string {
  return `${edge.role}::${edge.consumerId}`
}

export function ConsumerPills({ providerId }: { providerId: string | null }) {
  const [edges, setEdges] = useState<RoleConsumerEdge[]>([])
  const [openKey, setOpenKey] = useState<string | null>(null)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    const refresh = () => setEdges(loadProviderEdges(providerId || ''))
    refresh()
    window.addEventListener(ROLE_CONSUMERS_CHANGED_EVENT, refresh)
    return () => window.removeEventListener(ROLE_CONSUMERS_CHANGED_EVENT, refresh)
  }, [providerId])

  useEffect(() => {
    if (!openKey) return
    const edge = edges.find((row) => edgeKey(row) === openKey)
    if (!edge) return
    let cancelled = false
    setLoading(true)
    setError(false)
    void fetchAgentSuggestions(edge.consumerId, 'continue').then((chips) => {
      if (cancelled) return
      setSuggestions(chips)
      setLoading(false)
      setError(chips.length === 0)
    })
    return () => {
      cancelled = true
    }
  }, [openKey, edges])

  if (!providerId || edges.length === 0) return null

  return (
    <div
      className="border-b border-base-300 bg-base-200/40 px-2 py-1.5 sm:px-3"
      data-testid="consumer-pills"
    >
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <span className="text-base-content/60">Talking to this agent:</span>
        {edges.map((edge) => {
          const key = edgeKey(edge)
          const active = openKey === key
          return (
            <button
              key={key}
              type="button"
              className={`btn btn-xs rounded-full normal-case ${
                active ? 'btn-primary' : 'btn-ghost border border-base-300'
              }`}
              aria-expanded={active}
              onClick={() => {
                if (active) {
                  setOpenKey(null)
                } else {
                  setOpenKey(key)
                  setSuggestions([])
                }
              }}
              data-testid={`consumer-pill-${edge.consumerId}`}
            >
              {consumerLabel(edge.consumerId)}
              <span className="text-[10px] opacity-60">{edge.role}</span>
            </button>
          )
        })}
      </div>
      {openKey ? (
        <div className="mt-1.5 rounded-md border border-base-300 bg-base-100 p-2 text-xs" data-testid="consumer-pill-detail">
          {loading ? (
            <span className="text-base-content/60">Fetching suggestions…</span>
          ) : error ? (
            <span className="text-base-content/60">
              No suggestions served to this consumer yet.
            </span>
          ) : (
            <ul className="list-inside list-disc space-y-0.5 text-base-content/80">
              {suggestions.map((chip) => (
                <li key={chip}>{chip}</li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  )
}

export default ConsumerPills
