// #856 slice 14: rail row-operation surface moved verbatim from
// AgentSidebar — edit/duplicate/copy-id menu ops, recycle-bin drop
// resolution, and the two-stage delete (request + confirm). The
// deleteConfirm state stays page-owned; this hook owns the async ops.
import type { Dispatch, SetStateAction } from 'react'
import type { QueryClient } from '@tanstack/react-query'
import {
  createCustomBlueprint,
  createRemote,
  createTeamRoster,
  deleteCustomBlueprint,
  deleteRemote,
  deleteTeamRoster,
  type RemoteConnection,
} from '../../lib/api'
import {
  isUnassignedSection,
  moveAgentToSection,
  removeSectionMembership,
  sectionIdForAgent,
  type RailSectionsState,
} from '../../lib/railSections'
import {
  bumpRailIdToTop,
  insertRailIdAfter,
  mergeRailOrder,
} from '../../lib/railOrder'
import { markRailIdDeleted } from '../../lib/deletedRailIds'
import { copyTextToClipboard } from '../../lib/clipboard'
import { teamHideId } from '../../lib/teamRosters'
import { remoteHideId } from '../../lib/remotesCatalog'
import {
  assignedBlueprintId,
  loadAgentEdit,
  saveAgentEdit,
} from '../../lib/agentEdits'
import {
  copyableConversationId,
  duplicateName,
  duplicateRemoteId,
} from '../../lib/railContextMenu'
import { unpinAgent, type PinnedAgent } from '../../lib/pinnedAgents'
import { openTeamEditor } from '../../components/TeamEditor'
import { openSettingsSheet } from '../../components/SettingsSheet'
import type { RailRow, SidebarAgent } from './rows'
import type { ContextMenuState } from './rows'
import type { RailMenuKind } from '../../lib/railContextMenu'

export interface RailRowOpsOptions {
  agents: SidebarAgent[]
  orderedRows: RailRow[]
  pins: PinnedAgent[]
  teams: { id: string; name: string; members: { id: string; kind?: string; role?: string; source?: string; team_id?: string }[] }[]
  remotes: { id: string; title?: string }[]
  configuredRemotesList: (Partial<RemoteConnection> & { id?: string })[]
  fullRemotesData: { data?: (RemoteConnection & { id: string })[]; configured?: { id: string }[] }
  railOrder: string[]
  visibleRowIds: string[]
  sectionState: RailSectionsState
  deleteConfirm: ContextMenuState | null
  isPinnedId: (id: string | null | undefined) => boolean
  resolveMenuKind: (hideId: string, hinted?: RailMenuKind) => RailMenuKind
  openAgentSettings: (agent: { id: string; name: string }) => void
  closeMenu: () => void
  persistVisibleOrder: (nextVisible: string[]) => void
  queryClient: QueryClient
  setDeleteConfirm: Dispatch<SetStateAction<ContextMenuState | null>>
  setDeletedIds: Dispatch<SetStateAction<string[]>>
  setSectionState: Dispatch<SetStateAction<RailSectionsState>>
  setPins: Dispatch<SetStateAction<PinnedAgent[]>>
  onClose?: () => void
}

export function useRailRowOps(opts: RailRowOpsOptions) {
  const {
    agents,
    orderedRows,
    pins,
    teams,
    remotes,
    configuredRemotesList,
    fullRemotesData,
    railOrder,
    visibleRowIds,
    sectionState,
    deleteConfirm,
    isPinnedId,
    resolveMenuKind,
    openAgentSettings,
    closeMenu,
    persistVisibleOrder,
    queryClient,
    setDeleteConfirm,
    setDeletedIds,
    setSectionState,
    setPins,
    onClose,
  } = opts

  const editMenuRow = (row: ContextMenuState) => {
    if (row.kind === 'cli') return
    if (row.kind === 'team') {
      openTeamEditor({ teamId: row.entityId, teamName: row.agentName })
      closeMenu()
      return
    }
    if (row.kind === 'remote') {
      openSettingsSheet({ section: 'remotes' })
      closeMenu()
      onClose?.()
      return
    }
    openAgentSettings({ id: row.entityId, name: row.agentName })
  }

  const duplicateMenuRow = async (row: ContextMenuState) => {
    const name = duplicateName(row.agentName)
    try {
      if (row.kind === 'cli') return

      let sourceSectionId = sectionIdForAgent(row.agentId, sectionState)
      if (isUnassignedSection(sourceSectionId) && row.entityId && row.entityId !== row.agentId) {
        sourceSectionId = sectionIdForAgent(row.entityId, sectionState)
      }

      if (row.kind === 'team') {
        const source = teams.find((team) => team.id === row.entityId)
        const created = await createTeamRoster({
          name,
          members: (source?.members ?? []).map((member) => ({
            id: member.id,
            kind: member.kind || 'api',
            role: member.role || 'default',
            source: member.kind === 'team' ? `team:${member.team_id || member.id}` : `blueprint:${member.id}`,
            team_id: member.team_id,
          })),
        })
        await queryClient.invalidateQueries({ queryKey: ['team-rosters'] })
        const createdHide = teamHideId(created.id)
        if (!isUnassignedSection(sourceSectionId)) {
          setSectionState((current) => moveAgentToSection(current, createdHide, sourceSectionId))
        }
        const base = mergeRailOrder(railOrder, visibleRowIds)
        // #793: the duplicate lands at the top of the Unassigned order so it
        // is immediately visible (source section membership is preserved).
        persistVisibleOrder(bumpRailIdToTop(base, createdHide))
        closeMenu()
        return
      }
      if (row.kind === 'remote') {
        const source: Partial<RemoteConnection> | undefined =
          configuredRemotesList.find((remote) => remote.id === row.entityId) ||
          remotes.find((r) => r.id === row.entityId) ||
          fullRemotesData.data?.find((r) => r.id === row.entityId)

        const existingRemoteIds = new Set<string>()
        for (const r of configuredRemotesList) if (r.id) existingRemoteIds.add(r.id)
        for (const r of remotes) if (r.id) existingRemoteIds.add(r.id)
        for (const r of fullRemotesData.data ?? []) if (r.id) existingRemoteIds.add(r.id)
        for (const r of fullRemotesData.configured ?? []) if (r.id) existingRemoteIds.add(r.id)

        const newId = duplicateRemoteId(row.entityId, existingRemoteIds)
        const created = await createRemote({
          id: newId,
          title: name,
          kind: source?.kind || (row.entityId ? row.entityId.split('_')[0] : 'generic'),
          base_url: source?.base_url,
          api_key_env: source?.api_key_env,
          ui_url: source?.ui_url,
          herdr_mode: (source as any)?.herdr_mode,
          ssh_host: (source as any)?.ssh_host,
          ssh_user: (source as any)?.ssh_user,
          ssh_port: (source as any)?.ssh_port,
          ssh_identity_env: (source as any)?.ssh_identity_env,
          ssh_agent: (source as any)?.ssh_agent,
        })
        await queryClient.invalidateQueries({ queryKey: ['configured-remotes'] })
        await queryClient.invalidateQueries({ queryKey: ['remotes-list'] })
        await queryClient.invalidateQueries({ queryKey: ['remotes-list'] })
        const createdHide = remoteHideId(created.id)
        if (!isUnassignedSection(sourceSectionId)) {
          setSectionState((current) => moveAgentToSection(current, createdHide, sourceSectionId))
        }
        const base = mergeRailOrder(railOrder, visibleRowIds)
        persistVisibleOrder(insertRailIdAfter(base, createdHide, row.agentId))
        closeMenu()
        return
      }
      const sourceEdit = loadAgentEdit(row.entityId)
      const created = await createCustomBlueprint({
        name,
        description: `Copy of ${row.agentName}`,
        category: 'ai_assistants',
        tags: ['api'],
        kind: 'api',
        rail: true,
        source: 'add-agent',
        code: `# Copy of ${assignedBlueprintId(row.entityId)}\n`,
      })
      saveAgentEdit(created.id, {
        name,
        blueprintId: sourceEdit.blueprintId || assignedBlueprintId(row.entityId),
        role: sourceEdit.role,
        llmOverride: sourceEdit.llmOverride,
      })
      await queryClient.invalidateQueries({ queryKey: ['blueprints'] })
      await queryClient.invalidateQueries({ queryKey: ['custom-blueprints'] })
      if (!isUnassignedSection(sourceSectionId)) {
        setSectionState((current) => moveAgentToSection(current, created.id, sourceSectionId))
      }
      const base = mergeRailOrder(railOrder, visibleRowIds)
      persistVisibleOrder(insertRailIdAfter(base, created.id, row.agentId))
    } catch {
      /* caller / tests mock fetch; failures stay on the current row */
    }
    closeMenu()
  }

  const copyMenuConversationId = async (row: ContextMenuState) => {
    const id = copyableConversationId(row.kind, row.agentId, row.entityId)
    if (!id) {
      closeMenu()
      return
    }
    await copyTextToClipboard(id)
    closeMenu()
  }

  const handleDropOnRecycleBin = (fromId: string) => {
    const row = orderedRows.find((item) => item.id === fromId)
    const pin = pins.find((p) => p.id === fromId)
    const agent = agents.find((a) => a.id === fromId)
    const remote = remotes.find((r) => remoteHideId(r.id) === fromId || r.id === fromId)
    const team = teams.find((t) => teamHideId(t.id) === fromId || t.id === fromId)

    let kind: RailMenuKind = resolveMenuKind(fromId)
    let entityId = fromId
    let agentName = fromId

    if (row) {
      if (row.kind === 'remote') {
        kind = 'remote'
        entityId = row.remote.id
        agentName = row.remote.title
      } else if (row.kind === 'team') {
        kind = 'team'
        entityId = row.team.id
        agentName = row.team.name
      } else {
        kind = row.agent.kind === 'cli' ? 'cli' : resolveMenuKind(fromId)
        entityId = row.agent.id
        agentName = row.agent.name
      }
    } else if (remote) {
      kind = 'remote'
      entityId = remote.id
      agentName = remote.title || remote.id
    } else if (team) {
      kind = 'team'
      entityId = team.id
      agentName = team.name
    } else if (agent) {
      kind = agent.kind === 'cli' ? 'cli' : resolveMenuKind(fromId)
      entityId = agent.id
      agentName = agent.name
    } else if (pin) {
      agentName = pin.name
      entityId = pin.id
    }

    setDeleteConfirm({
      agentId: fromId,
      agentName,
      hidden: false,
      pinned: isPinnedId(fromId),
      x: 0,
      y: 0,
      kind,
      entityId,
    })
  }

  const requestDelete = (row: ContextMenuState) => {
    closeMenu()
    setDeleteConfirm(row)
  }

  const confirmDeleteRow = async () => {
    const row = deleteConfirm
    if (!row) return
    const hideId = row.agentId
    setPins((current) =>
      current.some((pin) => pin.id === hideId) ? unpinAgent(hideId, current) : current,
    )
    if (row.kind === 'remote') {
      try {
        await deleteRemote(row.entityId)
      } catch {
        /* local remove still applies */
      }
      await queryClient.invalidateQueries({ queryKey: ['configured-remotes'] })
      await queryClient.invalidateQueries({ queryKey: ['remotes-list'] })
      await queryClient.invalidateQueries({ queryKey: ['remotes-list'] })
    } else if (row.kind === 'team') {
      try {
        await deleteTeamRoster(row.entityId)
      } catch {
        /* local remove still applies */
      }
      await queryClient.invalidateQueries({ queryKey: ['team-rosters'] })
    } else if (row.kind === 'api') {
      try {
        await deleteCustomBlueprint(row.entityId)
      } catch {
        /* catalog seats are removed locally only */
      }
      await queryClient.invalidateQueries({ queryKey: ['blueprints'] })
      await queryClient.invalidateQueries({ queryKey: ['custom-blueprints'] })
    }
    // CLI: hide-or-remove from rail only — do not uninstall the binary.
    // #687 invariant: mark ONLY this row's rail id. The old double-mark of
    // row.entityId leaked a bare agent id into the shared deleted list, which
    // the (now namespaced-only) team/remote filters used to honor — deleting
    // one agent could remove a same-id remote/team row with it.
    setDeletedIds((current) => markRailIdDeleted(hideId, current))
    setSectionState((current) => removeSectionMembership(current, hideId))
    setDeleteConfirm(null)
  }

  return {
    editMenuRow,
    duplicateMenuRow,
    copyMenuConversationId,
    handleDropOnRecycleBin,
    requestDelete,
    confirmDeleteRow,
  }
}
