import { useContext, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { QueryClientContext } from '@tanstack/react-query'
import {
  createTeamRoster,
  fetchTeamRosters,
  updateTeamRoster,
} from '../lib/api'
import {
  seatingCtaLabel,
  type SupportNlSeatingCard,
  type SupportNlSeatingMember,
} from '../lib/supportNlSeating'
import { focusAgentChat } from '../lib/agentNotifications'

export interface SupportCreatedSeatingCardProps {
  card: SupportNlSeatingCard
}

function asRosterMembers(members: SupportNlSeatingMember[]) {
  return members.map((member) => ({
    id: member.id,
    name: member.name,
    kind: member.kind,
    role: member.role,
    source: member.source || `blueprint:${member.id}`,
  }))
}

/**
 * #1373: Support-drafted team/group seating. Persist uses /v1/team-rosters/.
 */
export default function SupportCreatedSeatingCard({
  card,
}: SupportCreatedSeatingCardProps) {
  const [persisted, setPersisted] = useState(card.persisted)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const queryClient = useContext(QueryClientContext)
  const navigate = useNavigate()

  const openTeam = () => {
    navigate(card.chatHref)
    focusAgentChat(card.id)
  }

  const persist = async () => {
    if (persisted || card.persisted) {
      openTeam()
      return
    }
    setBusy(true)
    setError('')
    try {
      const incoming = asRosterMembers(card.members)
      const list = await fetchTeamRosters()
      const existing = (list.data || []).find((row) => row.id === card.id)
      if (existing) {
        const seen = new Set(existing.members.map((row) => row.id))
        const merged = [...existing.members]
        for (const member of incoming) {
          if (seen.has(member.id)) continue
          seen.add(member.id)
          merged.push(member)
        }
        await updateTeamRoster(card.id, {
          name: existing.name || card.title,
          members: merged,
          wires: existing.wires,
          tools: existing.tools,
          blueprint_id: existing.blueprint_id,
          chief_of_staff_id: existing.chief_of_staff_id,
          chief_of_staff_instructions: existing.chief_of_staff_instructions,
        })
      } else {
        await createTeamRoster({
          name: card.title,
          members: incoming,
        })
      }
      setPersisted(true)
      await queryClient?.invalidateQueries({ queryKey: ['team-rosters'] })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not seat agents')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="card bg-base-100 border border-base-300 mt-2"
      data-testid="support-nl-seating-card"
      data-team-id={card.id}
    >
      <div className="card-body p-3 gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h4 className="card-title text-sm m-0">{card.title}</h4>
          {persisted ? (
            <span className="badge badge-success badge-sm" data-testid="support-nl-seating-usable">
              Seated
            </span>
          ) : (
            <span className="badge badge-warning badge-sm" data-testid="support-nl-seating-draft">
              Draft
            </span>
          )}
        </div>
        <p className="text-sm text-base-content/80 m-0" data-testid="support-nl-seating-members">
          {card.memberLabel}
        </p>
        <p className="text-xs text-base-content/60 m-0">
          Writes the existing team-roster store. No new Python class.
        </p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="btn btn-primary btn-xs"
            data-testid="support-nl-seat-team"
            disabled={busy}
            onClick={(event) => {
              event.preventDefault()
              event.stopPropagation()
              void persist()
            }}
          >
            {busy ? 'Seating…' : persisted ? 'Open' : seatingCtaLabel(card)}
          </button>
        </div>
        {error ? (
          <p className="text-xs text-error m-0" data-testid="support-nl-seating-error">
            {error}
          </p>
        ) : null}
      </div>
    </div>
  )
}
