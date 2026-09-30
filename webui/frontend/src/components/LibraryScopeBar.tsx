import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Select } from './DaisyUI'
import {
  createPresetBot,
  fetchRosterPacks,
  fetchScopedLibrary,
  fetchTeamRosters,
  importLibraryItem,
  importRosterPack,
  publishLibraryItem,
  publishRosterPack,
} from '../lib/api'
import {
  filterLibraryByScope,
  LIBRARY_SCOPE_OPTIONS,
  type LibraryScope,
} from '../lib/libraryScope'

const PRESET_BOTS = [
  { id: 'preset-support', name: 'Support' },
  { id: 'preset-researcher', name: 'Researcher' },
  { id: 'preset-reviewer', name: 'Reviewer' },
] as const

type ScopeRow = {
  id: string
  scope?: string
  title?: string
  name?: string
  item_key?: string
  kind?: string
  object?: string
  payload?: {
    needs_configuration?: Array<{ id?: string; reason?: string }>
    members?: unknown[]
  }
}

type TeamOption = { id: string; name: string }

function rowLabel(row: ScopeRow): string {
  return row.title || row.name || row.item_key || row.id
}

function sharedRows(rows: ScopeRow[]): ScopeRow[] {
  return rows.filter(
    (row) => row.object === 'shared_library.item' || row.object === 'team_roster_pack',
  )
}

export function LibraryScopeBar({
  surface,
  rosterId,
  itemKey,
  itemTitle,
  teamId,
}: {
  surface: 'library' | 'team'
  rosterId?: string
  itemKey?: string
  itemTitle?: string
  /** Roster id for Team scope. Same id as chat `?team=`, not an LLM-profile alias. */
  teamId?: string
}) {
  const [scope, setScope] = useState<LibraryScope>('personal')
  const [pickedTeam, setPickedTeam] = useState(teamId || '')
  const [notice, setNotice] = useState('')
  const queryClient = useQueryClient()
  const sharedScope = scope === 'personal' ? null : scope
  const activeTeam = scope === 'team' ? pickedTeam.trim() : ''

  const rostersQuery = useQuery({
    queryKey: ['team-rosters'],
    queryFn: fetchTeamRosters,
    enabled: scope === 'team',
    retry: 0,
  })

  const teams = useMemo<TeamOption[]>(() => {
    const rows = (rostersQuery.data?.data ?? [])
      .map((row) => ({ id: String(row.id || '').trim(), name: String(row.name || row.id || '').trim() }))
      .filter((row) => row.id)
    if (teamId && !rows.some((row) => row.id === teamId)) {
      rows.unshift({ id: teamId, name: teamId })
    }
    return rows
  }, [rostersQuery.data, teamId])

  useEffect(() => {
    if (scope !== 'team' || pickedTeam.trim()) return
    if (teamId) {
      setPickedTeam(teamId)
      return
    }
    if (teams.length === 1) setPickedTeam(teams[0].id)
  }, [scope, teamId, pickedTeam, teams])

  const packsQuery = useQuery({
    queryKey: ['library-scope', surface, sharedScope, activeTeam],
    enabled: sharedScope !== null && (sharedScope !== 'team' || Boolean(activeTeam)),
    retry: 0,
    queryFn: async () => {
      if (sharedScope === null) return []
      if (surface === 'team') {
        const body = await fetchRosterPacks(sharedScope, activeTeam || undefined)
        return sharedRows((body.data || []) as ScopeRow[])
      }
      const body = await fetchScopedLibrary(sharedScope, activeTeam || undefined)
      return sharedRows((body.data || []) as ScopeRow[])
    },
  })

  const visible = filterLibraryByScope(packsQuery.data ?? [], scope)
  const canPublish =
    (surface === 'team' ? Boolean(rosterId) : Boolean(itemKey)) &&
    (scope !== 'team' || Boolean(activeTeam))

  const publish = async () => {
    setNotice('')
    if (scope === 'team' && !activeTeam) {
      setNotice('Choose a team before publishing.')
      return
    }
    try {
      if (surface === 'team') {
        if (!rosterId || scope === 'personal') return
        await publishRosterPack({
          roster_id: rosterId,
          scope,
          ...(scope === 'team' ? { team_id: activeTeam } : {}),
        })
        setNotice('Roster pack published.')
      } else {
        if (!itemKey || scope === 'personal') return
        await publishLibraryItem({
          kind: 'blueprint',
          id: itemKey,
          scope,
          name: itemTitle || itemKey,
          ...(scope === 'team' ? { team_id: activeTeam } : {}),
        })
        setNotice('Blueprint published.')
      }
      await queryClient.invalidateQueries({ queryKey: ['library-scope'] })
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'Publish failed.')
    }
  }

  const importPack = async (id: string) => {
    setNotice('')
    try {
      const teamArg = scope === 'team' ? activeTeam || undefined : undefined
      const result =
        surface === 'team' ? await importRosterPack(id, teamArg) : await importLibraryItem(id, teamArg)
      const missing = result.needs_configuration || result.roster?.needs_configuration || []
      setNotice(
        missing.length
          ? `Imported. Missing: ${missing.map((row) => row.reason || row.id).filter(Boolean).join('; ')}`
          : 'Imported.',
      )
      await queryClient.invalidateQueries({ queryKey: ['library-scope'] })
      await queryClient.invalidateQueries({ queryKey: ['team-rosters'] })
      await queryClient.invalidateQueries({ queryKey: ['blueprints'] })
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'Import failed.')
    }
  }

  const addPreset = async (presetId: string) => {
    setNotice('')
    try {
      const seat = await createPresetBot(presetId)
      setNotice(`${seat.name || presetId} is on the rail.`)
      await queryClient.invalidateQueries({ queryKey: ['blueprints'] })
      await queryClient.invalidateQueries({ queryKey: ['blueprints-custom'] })
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'Could not add the preset.')
    }
  }

  return (
    <div className="space-y-2" data-testid={surface === 'team' ? 'roster-pack-scope' : 'library-scope'}>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Library scope">
        {LIBRARY_SCOPE_OPTIONS.map((option) => (
          <Button
            key={option.id}
            type="button"
            size="sm"
            variant={scope === option.id ? 'primary' : 'ghost'}
            aria-pressed={scope === option.id}
            onClick={() => setScope(option.id)}
          >
            {option.label}
          </Button>
        ))}
      </div>
      {scope === 'personal' ? (
        <p className="text-xs text-base-content/60">
          Mine keeps the personal library. Share and publish use Team or Organisation.
        </p>
      ) : (
        <div className="flex flex-wrap items-end gap-2">
          {scope === 'team' ? (
            <Select
              label="Team"
              aria-label="Team"
              size="sm"
              data-testid="library-team-picker"
              value={activeTeam}
              onChange={(event) => setPickedTeam(event.target.value)}
            >
              <option value="">Choose a team</option>
              {teams.map((team) => (
                <option key={team.id} value={team.id}>
                  {team.name || team.id}
                </option>
              ))}
            </Select>
          ) : null}
          <Button type="button" size="sm" disabled={!canPublish} onClick={() => void publish()}>
            {surface === 'team' ? 'Share' : 'Publish'}
          </Button>
        </div>
      )}
      {packsQuery.isError ? (
        <p className="text-xs text-error" role="alert">
          {packsQuery.error instanceof Error ? packsQuery.error.message : 'Could not load this scope.'}
        </p>
      ) : null}
      {visible.length > 0 ? (
        <ul className="text-sm space-y-1" aria-label="Shared library items">
          {visible.map((row) => (
            <li key={row.id} className="flex flex-wrap items-center gap-2">
              <span>{rowLabel(row)}</span>
              <Button type="button" size="sm" variant="ghost" onClick={() => void importPack(row.id)}>
                Import
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
      {surface === 'library' ? (
        <div className="flex flex-wrap gap-2" aria-label="Preset bots">
          {PRESET_BOTS.map((preset) => (
            <Button key={preset.id} type="button" size="sm" variant="ghost" onClick={() => void addPreset(preset.id)}>
              {`Add ${preset.name} to rail`}
            </Button>
          ))}
        </div>
      ) : null}
      {notice ? (
        <p className="text-xs text-base-content/70" data-testid="library-scope-notice">
          {notice}
        </p>
      ) : null}
    </div>
  )
}
