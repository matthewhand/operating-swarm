import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Pencil, Plus, Users } from 'lucide-react'
import { Alert, Button, Input, Modal, useToast } from '../DaisyUI'
import { createTeam, fetchTeams } from '../../lib/api'
import { notifyOverlayClosed } from '../../lib/chromeOverlay'
import { openTeamEditor } from '../TeamEditor'

export interface TeamsSheetProps {
  isOpen: boolean
  onClose: () => void
}

type SheetView = 'browse' | 'create'

/**
 * Right-docked Teams sheet over Chat (REQ-48; redesigned by #763).
 *
 * List-first: the primary view is a clean, readable list of registered
 * teams with per-row Edit (opening the team editor overlay). Creation is
 * a dedicated "+ New Team" flow in its own modal — no more inline form
 * crammed at the bottom of the list. Django /teams/ stays a power-user
 * link; this is not a React route that unmounts ChatPage.
 */
export default function TeamsSheet({ isOpen, onClose }: TeamsSheetProps) {
  const { success, error: toastError } = useToast()
  const queryClient = useQueryClient()
  const [view, setView] = useState<SheetView>('browse')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [llmProfile, setLlmProfile] = useState('default')

  const teamsQuery = useQuery({
    queryKey: ['overlay-teams'],
    queryFn: () => (fetchTeams ? fetchTeams() : Promise.resolve({ object: 'list' as const, data: [] })),
    enabled: isOpen,
    retry: 1,
  })
  const teams = teamsQuery.data?.data ?? []

  const createMutation = useMutation({
    mutationFn: createTeam,
    onSuccess: (team) => {
      success('Team created', `${team.id} is now an LLM-profile alias.`)
      setName('')
      setDescription('')
      setLlmProfile('default')
      setView('browse')
      void queryClient.invalidateQueries({ queryKey: ['overlay-teams'] })
    },
    onError: (err: unknown) => {
      const message = err instanceof Error ? err.message : 'Could not create team.'
      toastError('Team create failed', message)
    },
  })

  const handleClose = () => {
    onClose()
    notifyOverlayClosed()
  }

  const handleCreate = (event: FormEvent) => {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return
    createMutation.mutate({
      name: trimmed,
      description: description.trim() || undefined,
      llm_profile: llmProfile.trim() || undefined,
    })
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Teams"
      placement="end"
      size="sheet"
      className="flex min-h-0 flex-col"
    >
      {view === 'browse' ? (
        <div className="min-h-[24rem] space-y-5">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm text-base-content/70">
              Registered teams for multi-agent workflows and LLM-profile aliases.
            </p>
            <Button
              type="button"
              variant="primary"
              size="sm"
              aria-label="+ New Team"
              data-testid="teams-new-team"
              onClick={() => setView('create')}
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              New Team
            </Button>
          </div>

          {teamsQuery.isPending ? (
            <p className="text-sm text-base-content/60">Loading teams…</p>
          ) : teamsQuery.isError ? (
            <Alert type="warning" icon={<AlertCircle className="h-5 w-5" />}>
              <span className="text-sm">Could not load teams. Chat stays open behind this sheet.</span>
            </Alert>
          ) : teams.length === 0 ? (
            <Alert type="info" icon={<Users className="h-5 w-5" />}>
              <span className="text-sm">No teams registered yet — create one to get started.</span>
            </Alert>
          ) : (
            <ul className="space-y-2" aria-label="Registered teams">
              {teams.map((team) => (
                <li
                  key={team.id}
                  className="flex items-center gap-3 rounded-lg border border-base-300 bg-base-200/60 px-3 py-2"
                  data-testid={`teams-row-${team.id}`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="font-medium">{team.id}</div>
                    <div className="text-xs text-base-content/60">
                      {team.description || 'No description'} · {team.llm_profile}
                    </div>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="xs"
                    aria-label={`Edit ${team.id}`}
                    onClick={() => openTeamEditor({ teamId: team.id })}
                  >
                    <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                    Edit
                  </Button>
                </li>
              ))}
            </ul>
          )}

          <div className="modal-action mt-4">
            <a href="/teams/" className="btn btn-ghost btn-sm">
              Operator teams
            </a>
            <Button type="button" variant="ghost" size="sm" onClick={handleClose}>
              Close
            </Button>
          </div>
        </div>
      ) : (
        <Modal
          isOpen
          onClose={() => setView('browse')}
          title="New Team"
          size="sm"
        >
          <form className="space-y-3" onSubmit={handleCreate} aria-label="Create team">
            <Input
              label="Team name"
              name="team-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoComplete="off"
              required
            />
            <Input
              label="Description"
              name="team-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              autoComplete="off"
            />
            <Input
              label="LLM profile"
              name="team-llm-profile"
              value={llmProfile}
              onChange={(event) => setLlmProfile(event.target.value)}
              autoComplete="off"
            />
            <div className="modal-action">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setView('browse')}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                size="sm"
                disabled={!name.trim() || createMutation.isPending}
              >
                Create team
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </Modal>
  )
}
