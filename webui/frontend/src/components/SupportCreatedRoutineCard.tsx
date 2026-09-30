import { useContext, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { QueryClientContext } from '@tanstack/react-query'
import { createRoutine, type RoutineWrite } from '../lib/routines'
import {
  ADD_ROUTINE_LABEL,
  type SupportNlRoutineCard,
} from '../lib/supportNlRoutine'
import { focusAgentChat } from '../lib/agentNotifications'

export interface SupportCreatedRoutineCardProps {
  card: SupportNlRoutineCard
}

/**
 * #1373: Support-drafted routine. Persist is Add routine → existing routines API.
 */
export default function SupportCreatedRoutineCard({
  card,
}: SupportCreatedRoutineCardProps) {
  const [persisted, setPersisted] = useState(card.persisted)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const queryClient = useContext(QueryClientContext)
  const navigate = useNavigate()

  const openSeat = () => {
    navigate(card.chatHref)
    focusAgentChat(card.agentId)
  }

  const persist = async () => {
    if (persisted || card.persisted) {
      openSeat()
      return
    }
    setBusy(true)
    setError('')
    try {
      await createRoutine(card.agentId, {
        name: card.title,
        instruction: card.instruction,
        active: true,
        trigger: card.trigger as RoutineWrite['trigger'],
      })
      setPersisted(true)
      await queryClient?.invalidateQueries({ queryKey: ['routines'] })
      await queryClient?.invalidateQueries({ queryKey: ['routines', card.agentId] })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save routine')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="card bg-base-100 border border-base-300 mt-2"
      data-testid="support-nl-routine-card"
      data-agent-id={card.agentId}
    >
      <div className="card-body p-3 gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h4 className="card-title text-sm m-0">{card.title}</h4>
          {persisted ? (
            <span className="badge badge-success badge-sm" data-testid="support-nl-routine-usable">
              Usable
            </span>
          ) : (
            <span className="badge badge-warning badge-sm" data-testid="support-nl-routine-draft">
              Draft
            </span>
          )}
        </div>
        <p className="text-sm text-base-content/80 m-0" data-testid="support-nl-routine-agent">
          Agent: {card.agentId}
        </p>
        <p className="text-sm text-base-content/80 m-0" data-testid="support-nl-routine-trigger">
          {card.triggerLabel}
        </p>
        <p className="text-xs text-base-content/60 m-0" data-testid="support-nl-routine-instruction">
          {card.instruction}
        </p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="btn btn-primary btn-xs"
            data-testid="support-nl-add-routine"
            disabled={busy}
            onClick={(event) => {
              event.preventDefault()
              event.stopPropagation()
              void persist()
            }}
          >
            {busy ? 'Adding…' : persisted ? 'Open' : ADD_ROUTINE_LABEL}
          </button>
        </div>
        {error ? (
          <p className="text-xs text-error m-0" data-testid="support-nl-routine-error">
            {error}
          </p>
        ) : null}
      </div>
    </div>
  )
}
