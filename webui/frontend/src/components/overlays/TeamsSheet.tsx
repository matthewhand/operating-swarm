import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Users, Sparkles } from 'lucide-react'
import { Alert, Button, Input, Modal, useToast } from '../DaisyUI'
import { createTeam, fetchTeams } from '../../lib/api'
import { notifyOverlayClosed } from '../../lib/chromeOverlay'
import { useAgentStore } from '../../lib/agent-store'
import { TeamSelect } from '../AgentChat/TeamSelect'

export interface TeamsSheetProps {
  isOpen: boolean
  onClose: () => void
}

/**
 * Right-docked Teams sheet over Chat (REQ-48).
 *
 * Lists /v1/teams/ aliases in a DaisyUI modal-end. Django /teams/ stays a
 * power-user link — this is not a React route that unmounts ChatPage.
 */
export default function TeamsSheet({ isOpen, onClose }: TeamsSheetProps) {
  const { success, error: toastError } = useToast()
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [llmProfile, setLlmProfile] = useState('default')

  const routingStrategy = useAgentStore((s) => s.routingStrategy)
  const setRoutingStrategy = useAgentStore((s) => s.setRoutingStrategy)

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
      <div className="min-h-[24rem] space-y-5">
        <p className="text-sm text-base-content/70">
          Teams and routing configurations for multi-agent workflows and LLM-profile aliases.
        </p>

        {/* Team Selection */}
        <div className="space-y-2 rounded-box border border-base-300 p-3 bg-base-200/40">
          <h4 className="text-sm font-semibold">Active Team</h4>
          <p className="text-xs text-base-content/70">
            Switch active team or save current agent group as a team.
          </p>
          <TeamSelect />
        </div>

        {/* Routing Strategy */}
        <div className="space-y-2 rounded-box border border-base-300 p-3 bg-base-200/40">
          <h4 className="text-sm font-semibold">Routing Strategy</h4>
          <p className="text-xs text-base-content/70">
            Configure how messages are routed to specialists or agent teams.
          </p>
          <div className="join border border-base-300/80 rounded-full p-0.5 bg-base-200/60 shadow-xs flex flex-wrap">
            <button
              type="button"
              onClick={() => setRoutingStrategy('auto_route')}
              className={`btn btn-xs rounded-full px-2.5 ${routingStrategy === 'auto_route' ? 'btn-primary' : 'btn-ghost text-base-content/70'}`}
              title="Automatically route to specialist based on query patterns"
            >
              Auto Route
            </button>
            <button
              type="button"
              onClick={() => setRoutingStrategy('direct')}
              className={`btn btn-xs rounded-full px-2.5 ${routingStrategy === 'direct' ? 'btn-primary' : 'btn-ghost text-base-content/70'}`}
              title="Directly target selected agent"
            >
              Direct
            </button>
            <button
              type="button"
              onClick={() => setRoutingStrategy('router')}
              className={`btn btn-xs rounded-full px-2.5 ${routingStrategy === 'router' ? 'btn-primary' : 'btn-ghost text-base-content/70'}`}
              title="Route through Agent Router orchestrator"
            >
              Router
            </button>
            <button
              type="button"
              onClick={() => setRoutingStrategy('consensus')}
              className={`btn btn-xs rounded-full px-2.5 ${routingStrategy === 'consensus' ? 'btn-primary' : 'btn-ghost text-base-content/70'}`}
              title="Multi-agent panel fan-out and synthesized consensus"
            >
              <Sparkles className="w-3 h-3" />
              Consensus
            </button>
          </div>
        </div>

        {teamsQuery.isPending ? (
          <p className="text-sm text-base-content/60">Loading teams…</p>
        ) : teamsQuery.isError ? (
          <Alert type="warning" icon={<AlertCircle className="h-5 w-5" />}>
            <span className="text-sm">Could not load teams. Chat stays open behind this sheet.</span>
          </Alert>
        ) : teams.length === 0 ? (
          <Alert type="info" icon={<Users className="h-5 w-5" />}>
            <span className="text-sm">No teams registered yet.</span>
          </Alert>
        ) : (
          <ul className="space-y-2" aria-label="Registered teams">
            {teams.map((team) => (
              <li
                key={team.id}
                className="rounded-lg border border-base-300 bg-base-200/60 px-3 py-2"
              >
                <div className="font-medium">{team.id}</div>
                <div className="text-xs text-base-content/60">
                  {team.description || 'No description'} · {team.llm_profile}
                </div>
              </li>
            ))}
          </ul>
        )}

        <form className="space-y-3 rounded-box border border-base-300 p-3" onSubmit={handleCreate}>
          <h4 className="text-sm font-semibold">Create alias</h4>
          <Input
            label="Name"
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
          <Button type="submit" variant="primary" size="sm" disabled={!name.trim() || createMutation.isPending}>
            Create team
          </Button>
        </form>
      </div>

      <div className="modal-action mt-4">
        <a href="/teams/" className="btn btn-ghost btn-sm">
          Operator teams
        </a>
        <Button type="button" variant="ghost" size="sm" onClick={handleClose}>
          Close
        </Button>
      </div>
    </Modal>
  )
}
