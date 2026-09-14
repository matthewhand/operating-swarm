import { useContext, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { QueryClientContext } from '@tanstack/react-query'
import { FileCode2, EyeOff } from 'lucide-react'
import { Button, Textarea } from './DaisyUI'
import {
  VIEW_EDIT_CODE_LABEL,
  type SupportNlBlueprintCard,
} from '../lib/supportNlBlueprint'

export interface SupportCreatedBlueprintCardProps {
  card: SupportNlBlueprintCard
}

/**
 * REQ-158: Support-created team is usable; Python stays hidden until asked.
 */
export default function SupportCreatedBlueprintCard({
  card,
}: SupportCreatedBlueprintCardProps) {
  const [revealed, setRevealed] = useState(false)
  const queryClient = useContext(QueryClientContext)

  useEffect(() => {
    if (queryClient) {
      void queryClient.invalidateQueries({ queryKey: ['blueprints'] })
    }
  }, [queryClient, card.id])

  return (
    <div
      className="card bg-base-100 border border-base-300 mt-2"
      data-testid="support-nl-blueprint-card"
      data-blueprint-id={card.id}
    >
      <div className="card-body p-3 gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h4 className="card-title text-sm m-0">{card.title}</h4>
          {card.usable ? (
            <span className="badge badge-success badge-sm" data-testid="support-nl-usable">
              Usable
            </span>
          ) : (
            <span className="badge badge-warning badge-sm">Not on rail</span>
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
          <Link
            to={card.chatHref}
            className="btn btn-primary btn-xs"
            data-testid="support-nl-open-chat"
          >
            Open in chat
          </Link>
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
        {revealed ? (
          <Textarea
            aria-label="Blueprint Python source"
            data-testid="support-nl-code"
            className="min-h-40 font-mono text-xs"
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
