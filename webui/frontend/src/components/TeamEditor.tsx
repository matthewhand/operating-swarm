import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Modal, Select } from './DaisyUI'
import { fetchBlueprints, type Blueprint } from '../lib/api'
import { catalogLabel } from '../lib/supportAgent'
import { assignedTeamBlueprintId, saveTeamEdit } from '../lib/teamEdits'
import { fetchTeamRosters, parseTeamRosters } from '../lib/teamRosters'
import { openSettingsSheet } from './settings/kernel'
import PersonaRoster from './PersonaRoster'
import { declaredRosterForTeam } from '../lib/declaredRoster'
export {
  OPEN_TEAM_EDITOR_EVENT,
  openTeamEditor,
} from './teamEditorKernel'
export type { OpenTeamEditorDetail } from './teamEditorKernel'
import { LibraryScopeBar } from './LibraryScopeBar'

const EMPTY_BLUEPRINTS: Blueprint[] = []

export interface TeamEditorProps {
  isOpen: boolean
  onClose: () => void
  teamId: string | null
  teamName?: string | null
}

/**
 * Team-scoped editor overlay (REQ-81 / #433).
 *
 * Blueprint picks a catalog recipe for this team. **Edit blueprint…** opens
 * Settings → Blueprints with that item selected. Does not open the Teams
 * drop-zone roster UI.
 */
export default function TeamEditor({
  isOpen,
  onClose,
  teamId,
  teamName,
}: TeamEditorProps) {
  const id = (teamId || '').trim()
  const label = teamName?.trim() || id || 'team'
  const [blueprintId, setBlueprintId] = useState('')

  const blueprintsQuery = useQuery({
    queryKey: ['blueprints'],
    queryFn: fetchBlueprints,
    enabled: isOpen,
    retry: 1,
  })
  const teamsQuery = useQuery({
    queryKey: ['team-rosters'],
    queryFn: fetchTeamRosters,
    enabled: isOpen,
    retry: 1,
  })

  const catalog = useMemo(
    () => blueprintsQuery.data?.data ?? EMPTY_BLUEPRINTS,
    [blueprintsQuery.data],
  )
  // `parseTeamRosters` builds fresh objects per call, so this is a new object
  // every render — and the effect below depends on two of its fields. Memoized
  // on the query data, which is the only thing that can change the answer.
  const rosterTeam = useMemo(
    () => parseTeamRosters(teamsQuery.data).find((team) => team.id === id),
    [teamsQuery.data, id],
  )

  useEffect(() => {
    if (!isOpen || !id) return
    setBlueprintId(
      assignedTeamBlueprintId(
        { id, blueprintId: rosterTeam?.blueprintId || rosterTeam?.blueprint || '' },
        catalog.map((item) => item.id),
      ),
    )
  }, [isOpen, id, catalog, rosterTeam?.blueprintId, rosterTeam?.blueprint])

  const persistBlueprint = (nextId: string) => {
    setBlueprintId(nextId)
    saveTeamEdit(id, { blueprintId: nextId })
  }

  const roster = useMemo(
    () =>
      declaredRosterForTeam(
        { id, blueprintId, blueprint: blueprintId },
        catalog,
      ),
    [id, blueprintId, catalog],
  )

  const openBlueprintInSettings = () => {
    const assigned = blueprintId || assignedTeamBlueprintId({ id }, catalog.map((item) => item.id))
    if (!assigned) return
    onClose()
    openSettingsSheet({ section: 'blueprint', blueprintId: assigned })
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Edit ${label}`}
      placement="end"
      size="lg"
      className="flex min-h-0 flex-col"
    >
      <div
        id="os-team-editor"
        className="space-y-4 max-h-[calc(100vh-12rem)] overflow-y-auto pr-1"
        data-team-id={id || undefined}
        data-testid="team-editor"
      >
        <p className="text-sm text-base-content/70">
          This pane is only about this rig. Blueprint picks a catalog recipe
          — it is not the Rigs drop-zone and not Settings Remotes.
        </p>
        <LibraryScopeBar
          surface="team"
          rosterId={id || undefined}
          itemTitle={label}
          teamId={id || undefined}
        />

        <Select
          label="Blueprint"
          aria-label="Blueprint"
          value={blueprintId}
          onChange={(event) => persistBlueprint(event.target.value)}
          disabled={!id}
        >
          <option value="">Select a blueprint</option>
          {catalog.map((item) => (
            <option key={item.id} value={item.id}>
              {catalogLabel(item)}
            </option>
          ))}
        </Select>

        {roster ? (
          <div data-testid="team-editor-roster" className="space-y-2">
            <p className="text-sm font-medium">Declared roster</p>
            <PersonaRoster roster={roster} groupId={id} label={`${label} declared members`} />
            {roster.parsed ? (
              <ul className="text-sm text-base-content/70" aria-label="Persona names">
                {roster.personas.map((persona) => (
                  <li key={persona.name}>{persona.name}</li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-base-content/50">One generic seat — source has no named personas.</p>
            )}
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={!id || !blueprintId}
            onClick={openBlueprintInSettings}
          >
            Edit blueprint…
          </Button>
        </div>
      </div>

      <div className="modal-action mt-4">
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          Close
        </Button>
      </div>
    </Modal>
  )
}
