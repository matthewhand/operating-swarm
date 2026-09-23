import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle, Book } from 'lucide-react'
import { Alert, Button, Modal } from '../DaisyUI'
import { fetchBlueprints } from '../../lib/api'
import { agentLabel, supportFirstAgents } from '../../lib/supportAgent'
import { notifyOverlayClosed } from '../../lib/chromeOverlay'

export interface BlueprintsSheetProps {
  isOpen: boolean
  onClose: () => void
}

/**
 * Right-docked Blueprints sheet over Chat (REQ-48).
 *
 * Choosing a blueprint updates `?blueprint=` on the still-mounted Chat route.
 * Django `/blueprint-library/` stays a power-user link.
 */
export default function BlueprintsSheet({ isOpen, onClose }: BlueprintsSheetProps) {
  const navigate = useNavigate()
  const blueprintsQuery = useQuery({
    queryKey: ['blueprints'],
    queryFn: fetchBlueprints,
    enabled: isOpen,
    retry: 1,
  })
  const blueprints = supportFirstAgents(blueprintsQuery.data?.data ?? [])

  const handleClose = () => {
    onClose()
    notifyOverlayClosed()
  }

  const choose = (id: string) => {
    navigate(`/chat?blueprint=${encodeURIComponent(id)}`)
    handleClose()
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Blueprints"
      placement="end"
      size="sheet"
      className="flex min-h-0 flex-col"
    >
      <div className="min-h-[24rem] space-y-4">
        <p className="text-sm text-base-content/70">
          Discoverable agents. Opening one stays on Chat — this sheet does not
          replace the conversation.
        </p>
        {blueprintsQuery.isPending ? (
          <p className="text-sm text-base-content/60">Loading blueprints…</p>
        ) : blueprintsQuery.isError ? (
          <Alert type="warning" icon={<AlertCircle className="h-5 w-5" />}>
            <span className="text-sm">Could not load blueprints.</span>
          </Alert>
        ) : blueprints.length === 0 ? (
          <Alert type="info" icon={<Book className="h-5 w-5" />}>
            <span className="text-sm">No blueprints reported.</span>
          </Alert>
        ) : (
          <ul className="space-y-2" aria-label="Discoverable blueprints">
            {blueprints.map((blueprint) => (
              <li key={blueprint.id}>
                <button
                  type="button"
                  className="w-full rounded-lg border border-base-300 bg-base-200/60 px-3 py-2 text-left hover:bg-base-300/40"
                  onClick={() => choose(blueprint.id)}
                >
                  <span className="block font-medium">{agentLabel(blueprint)}</span>
                  {blueprint.description ? (
                    <span className="block text-xs text-base-content/60">{blueprint.description}</span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="modal-action mt-4">
        <a href="/blueprint-library/" className="btn btn-ghost btn-sm">
          Operator library
        </a>
        <Button type="button" variant="ghost" size="sm" onClick={handleClose}>
          Close
        </Button>
      </div>
    </Modal>
  )
}
