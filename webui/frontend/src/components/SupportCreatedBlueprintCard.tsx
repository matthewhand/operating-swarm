import { useContext, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { QueryClientContext } from '@tanstack/react-query'
import { FileCode2, EyeOff } from 'lucide-react'
import { Button, Textarea } from './DaisyUI'
import { createCustomBlueprint } from '../lib/api'
import {
  ADD_AS_AGENT_LABEL,
  SAVE_AS_BLUEPRINT_LABEL,
  VIEW_EDIT_CODE_LABEL,
  type SupportNlBlueprintCard,
} from '../lib/supportNlBlueprint'
import { focusAgentChat } from '../lib/agentNotifications'

export interface SupportCreatedBlueprintCardProps {
  card: SupportNlBlueprintCard
}

/**
 * REQ-158 / #440: Support-drafted team. Persist is Add as agent / Save as blueprint.
 */
export default function SupportCreatedBlueprintCard({
  card,
}: SupportCreatedBlueprintCardProps) {
  const [revealed, setRevealed] = useState(false)
  const [persisted, setPersisted] = useState(card.persisted)
  const [createdId, setCreatedId] = useState<string | null>(null)
  const [busy, setBusy] = useState<'add' | 'save' | null>(null)
  const [error, setError] = useState('')
  const queryClient = useContext(QueryClientContext)
  const navigate = useNavigate()

  const openSeat = (id: string) => {
    const href = id === card.id && card.chatHref ? card.chatHref : `/chat?blueprint=${encodeURIComponent(id)}`
    navigate(href)
    focusAgentChat(id)
  }

  const persist = async (asAgent: boolean) => {
    const activeId = createdId || card.id
    if (persisted || card.persisted) {
      if (asAgent) openSeat(activeId)
      return
    }
    setBusy(asAgent ? 'add' : 'save')
    setError('')
    try {
      const created = await createCustomBlueprint({
        id: card.id,
        name: card.title,
        description: card.description || card.graphLabel,
        code: card.code,
        category: 'api',
        tags: ['support-nl', 'handoff', 'team'],
        kind: 'api',
        rail: true,
        source: card.source || 'support-nl',
      })
      const targetId = created.id || card.id
      setCreatedId(targetId)
      setPersisted(true)
      await queryClient?.invalidateQueries({ queryKey: ['blueprints'] })
      await queryClient?.invalidateQueries({ queryKey: ['custom-blueprints'] })
      if (asAgent) {
        openSeat(targetId)
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div
      className={`card bg-base-100 border border-base-300 mt-2 ${
        revealed
          ? // #769: a deliberate "show me the code" breaks out of the bubble's
            // inline width — near-full chat-pane width, no cramped box.
            'support-nl-card--revealed -mx-3 sm:-mx-8 w-[calc(100%+1.5rem)] sm:w-[calc(100%+4rem)] max-w-none'
          : ''
      }`}
      data-testid="support-nl-blueprint-card"
      data-blueprint-id={card.id}
      data-revealed={revealed ? 'true' : undefined}
    >
      <div className="card-body p-3 gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h4 className="card-title text-sm m-0">{card.title}</h4>
          {persisted ? (
            <span className="badge badge-success badge-sm" data-testid="support-nl-usable">
              Usable
            </span>
          ) : (
            <span className="badge badge-warning badge-sm" data-testid="support-nl-draft">
              Draft
            </span>
          )}
        </div>
        <p className="text-sm text-base-content/80 m-0" data-testid="support-nl-graph">
          {card.graphLabel}
        </p>
        <p className="text-xs text-base-content/60 m-0">
          Under the hood this is a Python <code>ApiKindBase</code> class. You did
          not write Python.
        </p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="btn btn-primary btn-xs"
            data-testid="support-nl-add-agent"
            disabled={busy !== null}
            onClick={(event) => {
              event.preventDefault()
              event.stopPropagation()
              void persist(true)
            }}
          >
            {busy === 'add' ? 'Adding…' : ADD_AS_AGENT_LABEL}
          </button>
          {!persisted ? (
            <Button
              type="button"
              variant="outline"
              size="xs"
              data-testid="support-nl-save-blueprint"
              disabled={busy !== null}
              onClick={() => void persist(false)}
            >
              {busy === 'save' ? 'Saving…' : SAVE_AS_BLUEPRINT_LABEL}
            </Button>
          ) : null}
          <Button
            type="button"
            variant="outline"
            size="xs"
            aria-expanded={revealed}
            aria-label={revealed ? 'Hide code' : VIEW_EDIT_CODE_LABEL}
            data-testid="support-nl-view-edit-code"
            onClick={() => setRevealed((open) => !open)}
          >
            {revealed ? (
              <EyeOff className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <FileCode2 className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
            )}
            {revealed ? 'Hide code' : VIEW_EDIT_CODE_LABEL}
          </Button>
        </div>
        {error ? (
          <p className="text-xs text-error m-0" data-testid="support-nl-save-error">
            {error}
          </p>
        ) : null}
        {revealed ? (
          <Textarea
            aria-label="Blueprint Python source"
            data-testid="support-nl-code"
            className={`w-full font-mono text-xs ${
              revealed
                ? // #769: see the whole thing — generous floor, user-resizable,
                  // no max-height cap.
                  'min-h-96 resize-y leading-relaxed'
                : 'min-h-40'
            }`}
            value={card.code}
            readOnly
            spellCheck={false}
          />
        ) : (
          <p className="text-xs text-base-content/50 m-0" data-testid="support-nl-code-hidden">
            Code hidden by default. {VIEW_EDIT_CODE_LABEL} to reveal the generated
            class.
          </p>
        )}
      </div>
    </div>
  )
}
