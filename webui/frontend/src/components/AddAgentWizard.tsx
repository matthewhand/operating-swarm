import { useState, useId, useMemo, useRef } from 'react'
import { Terminal, Bot, Globe, Layers, Plus, ExternalLink, Edit3, X } from 'lucide-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Modal, Button, Alert } from './DaisyUI'
import {
  createCustomBlueprint,
  updateCustomBlueprint,
  createRemote,
  fetchBlueprints,
  fetchCliAgents,
  fetchCustomBlueprints,
  fetchRemotes,
} from '../lib/api'
import { OPENMOUSBOT_LABEL } from '../lib/remotesCatalog'
import { loadAgentEdit, saveAgentEdit } from '../lib/agentEdits'
import { FOLDER_FORMAT_ERROR, isValidFolderPath } from '../lib/agentFolder'
import {
  GITHUB_REPO_FORMAT_ERROR,
  emptyWorkspaceFields,
  isValidGithubRepo,
  loadAgentWorkspace,
  type AgentWorkspaceFields,
} from '../lib/agentWorkspace'
import { saveAgentSettings } from '../lib/agentSettings'
import AgentWorkspaceBinding from './AgentWorkspaceBinding'
import { RemoteSelect } from './RemoteSelect'
import { addAgentRemoteImpls, configuredRemotes } from '../lib/remotes'
import { remotesListForSelect, saveAgentRemoteBinding } from '../lib/agentRemote'

export type AgentKind = 'cli' | 'api' | 'remote' | 'blueprint'

export interface AddAgentWizardProps {
  isOpen: boolean
  onClose: () => void
  onCreated?: (agent: { id: string; name: string; kind: AgentKind }) => void
  onSelectAgent?: (agentId: string) => void
}

export { isValidFolderPath } from '../lib/agentFolder'

export interface ManageAgentItem {
  id: string
  name: string
  command?: string
  folder?: string
  githubRepo?: string
  description?: string
  prompt?: string
  isCustom: boolean
}

/**
 * REQ-184 / REQ-109 / REQ-164 / REQ-165 / REQ-167 / REQ-166: Add agent popup wizard.
 *
 * - Tabs: CLI | API | Remote. Remote lists impls (Hermes / OpenMousBot /
 *   Rakazo / Herdr / nested swarm) — not a parallel Herdr kind (REQ-203).
 * - Under each tab: shows existing list (empty state when none) AND create/edit fields on the same view.
 * - Esc / backdrop / close cancels without creating.
 * - Completing create bumps to top of unpinned and navigates.
 */
export default function AddAgentWizard({
  isOpen,
  onClose,
  onCreated,
  onSelectAgent,
}: AddAgentWizardProps) {
  const queryClient = useQueryClient()
  const titleId = useId()
  const firstInputRef = useRef<HTMLInputElement>(null)

  const [selectedKind, setSelectedKind] = useState<AgentKind>('cli')
  const [mode, setMode] = useState<'create' | 'edit'>('create')
  const [editingAgentId, setEditingAgentId] = useState<string | null>(null)
  const [editingAgentName, setEditingAgentName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // CLI fields
  const [cliName, setCliName] = useState('')
  const [cliCommand, setCliCommand] = useState('')
  const [cliFolder, setCliFolder] = useState('')
  const [cliGithubRepo, setCliGithubRepo] = useState('')
  const [cliWorkspacesEnabled, setCliWorkspacesEnabled] = useState(false)
  const [cliDescription, setCliDescription] = useState('')
  const [folderError, setFolderError] = useState<string | null>(null)
  const [repoError, setRepoError] = useState<string | null>(null)

  // API fields
  const [apiName, setApiName] = useState('')
  const [apiDescription, setApiDescription] = useState('')
  const [apiPrompt, setApiPrompt] = useState('')

  // Blueprint fields (first-class kind; same shape as API)
  const [bpName, setBpName] = useState('')
  const [bpDescription, setBpDescription] = useState('')
  const [bpPrompt, setBpPrompt] = useState('')

  // Remote fields
  const [remoteKind, setRemoteKind] = useState('omb')
  const [remoteBaseUrl, setRemoteBaseUrl] = useState('')
  const [remoteApiKey, setRemoteApiKey] = useState('')
  const [pickedRemoteId, setPickedRemoteId] = useState('')

  // Queries for existing agents
  const blueprintsQuery = useQuery({
    queryKey: ['blueprints'],
    queryFn: fetchBlueprints,
    enabled: isOpen,
    retry: 1,
  })

  const customBlueprintsQuery = useQuery({
    queryKey: ['custom-blueprints'],
    queryFn: fetchCustomBlueprints,
    enabled: isOpen,
    retry: 1,
  })

  const cliQuery = useQuery({
    queryKey: ['cli-agents'],
    queryFn: fetchCliAgents,
    enabled: isOpen,
    retry: 1,
  })

  const remotesQuery = useQuery({
    queryKey: ['remotes-list'],
    queryFn: fetchRemotes,
    enabled: isOpen,
    retry: 1,
  })
  const remotesCatalog = remotesListForSelect(remotesQuery.data)
  const configuredRemoteRows = configuredRemotes(remotesCatalog)
  const remoteImpls = addAgentRemoteImpls(remotesQuery.data)

  const resetFormFields = () => {
    setError(null)
    setFolderError(null)
    setRepoError(null)
    setSubmitting(false)
    setCliName('')
    setCliCommand('')
    setCliFolder('')
    setCliGithubRepo('')
    setCliWorkspacesEnabled(false)
    setCliDescription('')
    setApiName('')
    setApiDescription('')
    setApiPrompt('')
    setBpName('')
    setBpDescription('')
    setBpPrompt('')
    setRemoteKind('omb')
    setRemoteBaseUrl('')
    setRemoteApiKey('')
    setPickedRemoteId('')
    setEditingAgentId(null)
    setEditingAgentName('')
  }

  const handleClose = () => {
    resetFormFields()
    setSelectedKind('cli')
    setMode('create')
    onClose()
  }

  const handleSelectKind = (kind: AgentKind) => {
    setSelectedKind(kind)
    setError(null)
    setFolderError(null)
    setRepoError(null)
    if (mode === 'edit') {
      resetFormFields()
      setMode('create')
    }
  }

  // Aggregate CLI agents
  const cliAgents = useMemo<ManageAgentItem[]>(() => {
    const list: ManageAgentItem[] = []
    const seen = new Set<string>()

    const customList = customBlueprintsQuery.data?.data ?? []
    for (const item of customList) {
      if (item.category === 'cli' || item.tags?.includes('cli')) {
        const edits = loadAgentEdit(item.id)
        const name = edits.name || item.name || item.id
        const commandMatch = item.code?.match(/# Command:\s*(.*)/)
        const folderMatch = item.code?.match(/# Folder:\s*(.*)/)
        const command =
          edits.command ||
          item.command ||
          (commandMatch ? commandMatch[1].trim() : '') ||
          item.description ||
          ''
        const folder = edits.folder || (folderMatch ? folderMatch[1].trim() : '')
        seen.add(item.id)
        list.push({
          id: item.id,
          name,
          command,
          folder,
          githubRepo: edits.githubRepo || '',
          description: item.description,
          isCustom: true,
        })
      }
    }

    const rail = cliQuery.data?.rail ?? []
    for (const item of rail) {
      if (seen.has(item.id)) continue
      const edits = loadAgentEdit(item.id)
      const name = edits.name || item.name || item.id
      const command = edits.command || item.cli || ''
      const folder = edits.folder || ''
      seen.add(item.id)
      list.push({
        id: item.id,
        name,
        command: command || (item.installed ? 'installed' : 'not on PATH'),
        folder,
        githubRepo: edits.githubRepo || '',
        description: item.description,
        isCustom: false,
      })
    }

    const catalog = blueprintsQuery.data?.data ?? []
    for (const item of catalog) {
      if (seen.has(item.id)) continue
      if (item.category === 'cli' || item.tags?.includes('cli')) {
        const edits = loadAgentEdit(item.id)
        const name = edits.name || item.name || item.id
        const command = edits.command || item.description || ''
        const folder = edits.folder || ''
        seen.add(item.id)
        list.push({
          id: item.id,
          name,
          command,
          folder,
          githubRepo: edits.githubRepo || '',
          description: item.description,
          isCustom: false,
        })
      }
    }

    return list
  }, [customBlueprintsQuery.data, cliQuery.data, blueprintsQuery.data])

  // Aggregate API agents
  const apiAgents = useMemo<ManageAgentItem[]>(() => {
    const list: ManageAgentItem[] = []
    const seen = new Set<string>()

    const customList = customBlueprintsQuery.data?.data ?? []
    for (const item of customList) {
      if (item.category === 'cli' || item.tags?.includes('cli')) continue
      if (item.category === 'blueprint' || item.tags?.includes('blueprint')) continue
      const edits = loadAgentEdit(item.id)
      const name = edits.name || item.name || item.id
      seen.add(item.id)
      list.push({
        id: item.id,
        name,
        description: item.description || '',
        prompt: item.code || '',
        isCustom: true,
      })
    }

    const catalog = blueprintsQuery.data?.data ?? []
    for (const item of catalog) {
      if (seen.has(item.id)) continue
      if (item.category === 'cli' || item.tags?.includes('cli')) continue
      if (item.category === 'blueprint' || item.tags?.includes('blueprint')) continue
      const edits = loadAgentEdit(item.id)
      const name = edits.name || item.name || item.id
      seen.add(item.id)
      list.push({
        id: item.id,
        name,
        description: item.description || '',
        isCustom: false,
      })
    }

    return list
  }, [customBlueprintsQuery.data, blueprintsQuery.data])

  const handleStartAddNew = () => {
    resetFormFields()
    setMode('create')
    setTimeout(() => {
      firstInputRef.current?.focus()
    }, 0)
  }

  // Aggregate blueprint agents (first-class kind)
  const blueprintAgents = useMemo<ManageAgentItem[]>(() => {
    const list: ManageAgentItem[] = []
    const seen = new Set<string>()

    const customList = customBlueprintsQuery.data?.data ?? []
    for (const item of customList) {
      if (item.category === 'blueprint' || item.tags?.includes('blueprint')) {
        const edits = loadAgentEdit(item.id)
        const name = edits.name || item.name || item.id
        seen.add(item.id)
        list.push({
          id: item.id,
          name,
          description: item.description || '',
          prompt: item.code || '',
          isCustom: true,
        })
      }
    }

    const catalog = blueprintsQuery.data?.data ?? []
    for (const item of catalog) {
      if (seen.has(item.id)) continue
      if (item.category === 'blueprint' || item.tags?.includes('blueprint')) {
        const edits = loadAgentEdit(item.id)
        const name = edits.name || item.name || item.id
        seen.add(item.id)
        list.push({
          id: item.id,
          name,
          description: item.description || '',
          isCustom: false,
        })
      }
    }

    return list
  }, [customBlueprintsQuery.data, blueprintsQuery.data])

  const handleStartEdit = (agent: ManageAgentItem) => {
    setError(null)
    setFolderError(null)
    setRepoError(null)
    setEditingAgentId(agent.id)
    setEditingAgentName(agent.name)
    setMode('edit')
    if (selectedKind === 'cli') {
      const stored = loadAgentWorkspace(agent.id)
      setCliName(agent.name)
      setCliCommand(agent.command || '')
      setCliFolder(agent.folder || stored.folder)
      setCliGithubRepo(agent.githubRepo || stored.githubRepo)
      setCliWorkspacesEnabled(stored.workspacesEnabled)
      setCliDescription(agent.description || '')
    } else if (selectedKind === 'api' || selectedKind === 'blueprint') {
      if (selectedKind === 'blueprint') {
        setBpName(agent.name)
        setBpDescription(agent.description || '')
        setBpPrompt(agent.prompt || '')
      } else {
        setApiName(agent.name)
        setApiDescription(agent.description || '')
        setApiPrompt(agent.prompt || '')
      }
    }
    setTimeout(() => {
      firstInputRef.current?.focus()
    }, 0)
  }

  const handleCancelEdit = () => {
    resetFormFields()
    setMode('create')
  }

  const handleOpenAgent = (agentId: string) => {
    if (onSelectAgent) {
      onSelectAgent(agentId)
    } else if (typeof window !== 'undefined') {
      window.location.href = `/chat?blueprint=${encodeURIComponent(agentId)}`
    }
    handleClose()
  }

  const handleConnectRemote = (remoteId: string, remoteName: string) => {
    saveAgentRemoteBinding(remoteId, {
      id: remoteId,
      kind: remoteId,
    })
    onCreated?.({
      id: remoteId,
      name: remoteName,
      kind: 'remote',
    })
    handleClose()
  }

  const handleCancelForm = () => {
    resetFormFields()
    setMode('create')
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError(null)

    if (selectedKind === 'cli' && cliFolder.trim() && !isValidFolderPath(cliFolder)) {
      setFolderError(FOLDER_FORMAT_ERROR)
      return
    }
    if (selectedKind === 'cli' && cliGithubRepo.trim() && !isValidGithubRepo(cliGithubRepo)) {
      setRepoError(GITHUB_REPO_FORMAT_ERROR)
      return
    }

    setSubmitting(true)

    try {
      if (selectedKind === 'cli') {
        const name = cliName.trim()
        const command = cliCommand.trim()
        const folder = cliFolder.trim()
        const githubRepo = cliGithubRepo.trim()
        const description = cliDescription.trim()
        if (!name) throw new Error('Agent name is required')
        if (!command) throw new Error('CLI command or binary is required')

        const folderComment = folder ? `# Folder: ${folder}
` : ''
        const code = `# CLI agent: ${name}
# Command: ${command}
${folderComment}`

        if (mode === 'create') {
          const created = await createCustomBlueprint({
            name,
            description: description || `CLI: ${command}`,
            category: 'cli',
            code,
            tags: ['cli'],
            kind: 'cli',
            command,
            rail: true,
            source: 'add-agent',
          })

          saveAgentEdit(created.id, {
            name,
            command,
            folder,
            githubRepo,
            workspacesEnabled: false,
          })
          await saveAgentSettings(created.id, { folder })

          await queryClient.invalidateQueries({ queryKey: ['blueprints'] })
          await queryClient.invalidateQueries({ queryKey: ['custom-blueprints'] })
          await queryClient.invalidateQueries({ queryKey: ['cli-agents'] })
          onCreated?.({ id: created.id, name: created.name, kind: 'cli' })
          handleClose()
        } else if (mode === 'edit' && editingAgentId) {
          saveAgentEdit(editingAgentId, {
            name,
            command,
            folder,
            githubRepo,
            workspacesEnabled: false,
          })
          await saveAgentSettings(editingAgentId, { folder })

          try {
            await updateCustomBlueprint(editingAgentId, {
              name,
              description: description || `CLI: ${command}`,
              code,
              kind: 'cli',
              command,
              rail: true,
            })
          } catch {
            // Local edits already saved via saveAgentEdit
          }

          await queryClient.invalidateQueries({ queryKey: ['blueprints'] })
          await queryClient.invalidateQueries({ queryKey: ['custom-blueprints'] })
          await queryClient.invalidateQueries({ queryKey: ['cli-agents'] })
          resetFormFields()
          setMode('create')
        }
      } else if (selectedKind === 'api' || selectedKind === 'blueprint') {
        const isBp = selectedKind === 'blueprint'
        const name = (isBp ? bpName : apiName).trim()
        const description = (isBp ? bpDescription : apiDescription).trim()
        const prompt = (isBp ? bpPrompt : apiPrompt).trim()
        if (!name) throw new Error('Agent name is required')

        if (mode === 'create') {
          const created = await createCustomBlueprint({
            name,
            description,
            category: isBp ? 'blueprint' : 'ai_assistants',
            code: prompt || `# ${isBp ? 'Blueprint' : 'API Assistant'}: ${name}
`,
            tags: [isBp ? 'blueprint' : 'api'],
            kind: isBp ? 'blueprint' : 'api',
            rail: true,
            source: 'add-agent',
          })

          saveAgentEdit(created.id, { name })

          await queryClient.invalidateQueries({ queryKey: ['blueprints'] })
          await queryClient.invalidateQueries({ queryKey: ['custom-blueprints'] })
          onCreated?.({ id: created.id, name: created.name, kind: isBp ? 'blueprint' : 'api' })
          handleClose()
        } else if (mode === 'edit' && editingAgentId) {
          saveAgentEdit(editingAgentId, { name })

          try {
            await updateCustomBlueprint(editingAgentId, {
              name,
              description,
              code: prompt || `# ${isBp ? 'Blueprint' : 'API Assistant'}: ${name}
`,
              kind: isBp ? 'blueprint' : 'api',
              rail: true,
            })
          } catch {
            // Local edits already saved via saveAgentEdit
          }

          await queryClient.invalidateQueries({ queryKey: ['blueprints'] })
          await queryClient.invalidateQueries({ queryKey: ['custom-blueprints'] })
          resetFormFields()
          setMode('create')
        }
      } else if (selectedKind === 'remote') {
        const baseUrl = remoteBaseUrl.trim()
        if (baseUrl) {
          const implId = remoteKind === 'generic' ? 'hermes' : remoteKind
          const created = await createRemote({
            kind: implId,
            ...(implId === 'herdr' && !baseUrl ? { herdr_mode: 'local' } : { base_url: baseUrl }),
            ...(remoteApiKey.trim() ? { api_key: remoteApiKey.trim() } : {}),
          })

          saveAgentRemoteBinding(created.id, {
            id: created.id,
            kind: created.kind || created.id,
          })
          await queryClient.invalidateQueries({ queryKey: ['configured-remotes'] })
          await queryClient.invalidateQueries({ queryKey: ['settings-remotes'] })
          await queryClient.invalidateQueries({ queryKey: ['remotes-list'] })
          const implLabel =
            remoteImpls.find((row) => row.id === implId)?.label || created.id
          onCreated?.({
            id: created.id,
            name: implLabel,
            kind: 'remote',
          })
          handleClose()
        } else if (pickedRemoteId) {
          const picked = configuredRemoteRows.find((row) => row.id === pickedRemoteId)
          if (!picked) throw new Error('Select a configured remote')
          saveAgentRemoteBinding(picked.id, {
            id: picked.id,
            kind: picked.kind || picked.id,
          })
          onCreated?.({
            id: picked.id,
            name: picked.label || picked.title || picked.id,
            kind: 'remote',
          })
          handleClose()
        } else if (remoteKind === 'herdr') {
          const created = await createRemote({
            kind: 'herdr',
            herdr_mode: 'local',
            ...(remoteApiKey.trim() ? { api_key: remoteApiKey.trim() } : {}),
          })
          saveAgentRemoteBinding(created.id, {
            id: created.id,
            kind: created.kind || created.id,
          })
          await queryClient.invalidateQueries({ queryKey: ['configured-remotes'] })
          await queryClient.invalidateQueries({ queryKey: ['settings-remotes'] })
          await queryClient.invalidateQueries({ queryKey: ['remotes-list'] })
          onCreated?.({
            id: created.id,
            name: remoteImpls.find((row) => row.id === 'herdr')?.label || 'Herdr',
            kind: 'remote',
          })
          handleClose()
        } else if (configuredRemoteRows.length > 0) {
          throw new Error('Select a configured remote')
        } else {
          throw new Error('Base URL is required')
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save agent')
    } finally {
      setSubmitting(false)
    }
  }

  const currentAgents =
    selectedKind === 'cli' ? cliAgents : selectedKind === 'blueprint' ? blueprintAgents : apiAgents

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      size="lg"
      placement="middle"
      aria-label="Add agent wizard"
    >
      <div className="space-y-4 max-h-[82vh] overflow-y-auto pr-1" data-testid="add-agent-wizard">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-base-300 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Plus className="h-4 w-4" aria-hidden="true" />
            </div>
            <div>
              <h3 id={titleId} className="text-base font-semibold">
                Add Agent
              </h3>
              <p className="text-xs text-base-content/60">
                Browse existing agents or configure a new one
              </p>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-xs btn-circle text-base-content/60 hover:text-base-content"
            aria-label="Close"
            onClick={handleClose}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        {/* Tabs */}
        <div
          role="tablist"
          className="tabs tabs-boxed bg-base-200/70 p-1 rounded-xl"
          aria-label="Agent kinds"
        >
          <button
            type="button"
            role="tab"
            aria-selected={selectedKind === 'cli'}
            className={`tab gap-2 flex-1 font-semibold text-xs sm:text-sm transition ${
              selectedKind === 'cli' ? 'tab-active' : ''
            }`}
            onClick={() => handleSelectKind('cli')}
            data-testid="kind-option-cli"
          >
            <Terminal className="h-4 w-4" aria-hidden="true" />
            <span>CLI</span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={selectedKind === 'api'}
            className={`tab gap-2 flex-1 font-semibold text-xs sm:text-sm transition ${
              selectedKind === 'api' ? 'tab-active' : ''
            }`}
            onClick={() => handleSelectKind('api')}
            data-testid="kind-option-api"
          >
            <Bot className="h-4 w-4" aria-hidden="true" />
            <span>API</span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={selectedKind === 'blueprint'}
            className={`tab gap-2 flex-1 font-semibold text-xs sm:text-sm transition ${
              selectedKind === 'blueprint' ? 'tab-active' : ''
            }`}
            onClick={() => handleSelectKind('blueprint')}
            data-testid="kind-option-blueprint"
          >
            <Layers className="h-4 w-4" aria-hidden="true" />
            <span>Blueprint</span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={selectedKind === 'remote'}
            className={`tab gap-2 flex-1 font-semibold text-xs sm:text-sm transition ${
              selectedKind === 'remote' ? 'tab-active' : ''
            }`}
            onClick={() => handleSelectKind('remote')}
            data-testid="kind-option-remote"
          >
            <Globe className="h-4 w-4" aria-hidden="true" />
            <span>Remote</span>
          </button>
        </div>

        {error ? (
          <Alert type="error" className="py-2 text-xs">
            {error}
          </Alert>
        ) : null}

        {/* Tab content: 1. Existing List (Manage) */}
        <hr className="border-base-300" data-testid="manage-surface-divider" />
        <div className="space-y-3" data-testid="manage-agent-surface">
          {selectedKind === 'remote' ? (
            configuredRemoteRows.length === 0 ? (
              <div
                className="rounded-xl border border-dashed border-base-300 py-6 text-center"
                data-testid="empty-manage-state"
              >
                <div className="mx-auto flex h-9 w-9 items-center justify-center rounded-full bg-base-200 text-base-content/50">
                  <Globe className="h-4.5 w-4.5" />
                </div>
                <p className="mt-2 text-sm font-medium">No remotes configured yet</p>
                <p className="mt-1 text-xs text-base-content/60">
                  Connect Hermes, {OPENMOUSBOT_LABEL}, Rakazo, Herdr, or nested
                  open-swarm — implementations of Remote, not extra kinds.
                </p>
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  className="mt-2"
                  onClick={handleStartAddNew}
                  data-testid="empty-add-btn"
                >
                  Add Remote Agent
                </Button>
              </div>
            ) : (
              <div className="space-y-2.5" data-testid="manage-agent-list">
                <div className="flex items-center justify-between text-xs font-semibold text-base-content/70">
                  <span>Configured Remotes ({configuredRemoteRows.length})</span>
                </div>
                <RemoteSelect
                  remotes={remotesCatalog}
                  value={pickedRemoteId}
                  onChange={setPickedRemoteId}
                  label="Remote"
                />
                <div className="max-h-36 overflow-y-auto space-y-1.5 pr-1">
                  {configuredRemoteRows.map((row) => (
                    <div
                      key={row.id}
                      className="flex items-center justify-between rounded-lg border border-base-300 bg-base-100 p-2.5 hover:bg-base-200/40"
                      data-testid={`agent-row-${row.id}`}
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-purple-500/10 text-purple-500">
                          <Globe className="h-3.5 w-3.5" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs font-semibold truncate leading-tight">
                            {row.label || row.title || row.id}
                          </p>
                          <p className="text-[11px] text-base-content/60 truncate font-mono mt-0.5">
                            {row.base_url || row.id}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0 ml-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="xs"
                          onClick={() =>
                            handleConnectRemote(row.id, row.label || row.title || row.id)
                          }
                          data-testid={`open-agent-${row.id}`}
                          aria-label={`Open ${row.label || row.title || row.id}`}
                        >
                          <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                          Connect
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
          ) : currentAgents.length === 0 ? (
            <div
              className="rounded-xl border border-dashed border-base-300 py-6 text-center"
              data-testid="empty-manage-state"
            >
              <div className="mx-auto flex h-9 w-9 items-center justify-center rounded-full bg-base-200 text-base-content/50">
                {selectedKind === 'cli' ? (
                  <Terminal className="h-4.5 w-4.5" />
                ) : selectedKind === 'blueprint' ? (
                  <Layers className="h-4.5 w-4.5" />
                ) : (
                  <Bot className="h-4.5 w-4.5" />
                )}
              </div>
              <p className="mt-2 text-sm font-medium">
                {selectedKind === 'cli'
                  ? 'No CLI agents yet'
                  : selectedKind === 'blueprint'
                    ? 'No Blueprint agents yet'
                    : 'No API agents yet'}
              </p>
              <p className="mt-1 text-xs text-base-content/60">
                Get started by creating your first{' '}
                {selectedKind === 'cli' ? 'CLI' : selectedKind === 'blueprint' ? 'Blueprint' : 'API'}{' '}
                agent below.
              </p>
              <Button
                type="button"
                variant="ghost"
                size="xs"
                className="mt-2"
                onClick={handleStartAddNew}
                data-testid="empty-add-btn"
              >
                Add{' '}
                {selectedKind === 'cli' ? 'CLI' : selectedKind === 'blueprint' ? 'Blueprint' : 'API'}{' '}
                Agent
              </Button>
            </div>
          ) : (
            <div className="space-y-2" data-testid="manage-agent-list">
              <div className="flex items-center justify-between text-xs font-semibold text-base-content/70">
                <span>
                  Existing {selectedKind === 'cli' ? 'CLI' : 'API'} Agents ({currentAgents.length})
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  onClick={handleStartAddNew}
                  data-testid="add-new-agent-btn"
                >
                  <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                  New agent
                </Button>
              </div>
              <div className="max-h-40 overflow-y-auto space-y-1.5 pr-1">
                {currentAgents.map((agent) => (
                  <div
                    key={agent.id}
                    className="flex items-center justify-between rounded-lg border border-base-300 bg-base-100 p-2.5 hover:bg-base-200/40"
                    data-testid={`agent-row-${agent.id}`}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div
                        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${
                          selectedKind === 'cli'
                            ? 'bg-emerald-500/10 text-emerald-500'
                            : selectedKind === 'blueprint'
                              ? 'bg-violet-500/10 text-violet-500'
                              : 'bg-sky-500/10 text-sky-500'
                        }`}
                      >
                        {selectedKind === 'cli' ? (
                          <Terminal className="h-3.5 w-3.5" />
                        ) : selectedKind === 'blueprint' ? (
                          <Layers className="h-3.5 w-3.5" />
                        ) : (
                          <Bot className="h-3.5 w-3.5" />
                        )}
                      </div>
                      <div className="min-w-0">
                        <p className="text-xs font-semibold truncate leading-tight">{agent.name}</p>
                        <p className="text-[11px] text-base-content/60 truncate font-mono mt-0.5">
                          {selectedKind === 'cli'
                            ? agent.command || 'CLI'
                            : selectedKind === 'blueprint'
                              ? agent.description || 'Blueprint'
                              : agent.description || 'API Assistant'}
                          {agent.folder ? ` · ${agent.folder}` : ''}
                          {agent.githubRepo ? ` · ${agent.githubRepo}` : ''}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0 ml-2">
                      <Button
                        type="button"
                        variant="ghost"
                        size="xs"
                        onClick={() => handleStartEdit(agent)}
                        data-testid={`edit-agent-${agent.id}`}
                        aria-label={`Edit ${agent.name}`}
                      >
                        <Edit3 className="h-3.5 w-3.5" aria-hidden="true" />
                        Edit
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="xs"
                        onClick={() => handleOpenAgent(agent.id)}
                        data-testid={`open-agent-${agent.id}`}
                        aria-label={`Open ${agent.name}`}
                      >
                        <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                        Open
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Tab content: 2. Create / Edit Section */}
        <div className="border-t border-base-300 pt-3.5">
          <form onSubmit={handleSubmit} className="space-y-3.5" data-testid="add-agent-form">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold uppercase tracking-wider text-base-content/70">
                {mode === 'edit'
                  ? `Edit ${
                      selectedKind === 'cli' ? 'CLI' : selectedKind === 'blueprint' ? 'Blueprint' : 'API'
                    } Agent: ${editingAgentName}`
                  : `Add New ${
                      selectedKind === 'cli'
                        ? 'CLI'
                        : selectedKind === 'api'
                          ? 'API'
                          : selectedKind === 'blueprint'
                            ? 'Blueprint'
                            : 'Remote'
                    } Agent`}
              </h4>
              {mode === 'edit' ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  onClick={handleCancelEdit}
                  data-testid="cancel-edit-btn"
                >
                  Cancel edit
                </Button>
              ) : null}
            </div>

            {selectedKind === 'cli' ? (
              <>
                <div className="space-y-1">
                  <label className="block text-xs font-medium text-base-content/80">
                    Agent Name <span className="text-error">*</span>
                  </label>
                  <input
                    ref={firstInputRef}
                    type="text"
                    className="input input-sm input-bordered w-full"
                    placeholder="e.g. Claude Code CLI"
                    value={cliName}
                    onChange={(e) => setCliName(e.target.value)}
                    required
                    autoFocus
                    aria-label="Agent name"
                    data-testid="input-cli-name"
                  />
                </div>
                <div className="space-y-1">
                  <label className="block text-xs font-medium text-base-content/80">
                    Command or Executable <span className="text-error">*</span>
                  </label>
                  <input
                    type="text"
                    className="input input-sm input-bordered w-full font-mono text-xs"
                    placeholder="e.g. claude, bash, python"
                    value={cliCommand}
                    onChange={(e) => setCliCommand(e.target.value)}
                    required
                    aria-label="CLI command"
                    data-testid="input-cli-command"
                  />
                </div>
                <AgentWorkspaceBinding
                  kind="cli"
                  value={{
                    folder: cliFolder,
                    githubRepo: cliGithubRepo,
                    workspacesEnabled: cliWorkspacesEnabled,
                  }}
                  folderError={folderError}
                  repoError={repoError}
                  onChange={(next: AgentWorkspaceFields) => {
                    setCliFolder(next.folder)
                    setCliGithubRepo(next.githubRepo)
                    setCliWorkspacesEnabled(false)
                    if (next.folder && !isValidFolderPath(next.folder)) {
                      setFolderError(FOLDER_FORMAT_ERROR)
                    } else {
                      setFolderError(null)
                    }
                    if (next.githubRepo && !isValidGithubRepo(next.githubRepo)) {
                      setRepoError(GITHUB_REPO_FORMAT_ERROR)
                    } else {
                      setRepoError(null)
                    }
                  }}
                />
                <div className="space-y-1">
                  <label className="block text-xs font-medium text-base-content/80">
                    Description (optional)
                  </label>
                  <input
                    type="text"
                    className="input input-sm input-bordered w-full text-xs"
                    placeholder="Brief description of what this agent does"
                    value={cliDescription}
                    onChange={(e) => setCliDescription(e.target.value)}
                    aria-label="Description"
                  />
                </div>
              </>
            ) : null}

            {selectedKind === 'api' ? (
              <>
                <div className="space-y-1">
                  <label className="block text-xs font-medium text-base-content/80">
                    Agent Name <span className="text-error">*</span>
                  </label>
                  <input
                    ref={firstInputRef}
                    type="text"
                    className="input input-sm input-bordered w-full"
                    placeholder="e.g. Research Analyst"
                    value={apiName}
                    onChange={(e) => setApiName(e.target.value)}
                    required
                    autoFocus
                    aria-label="Agent name"
                    data-testid="input-api-name"
                  />
                </div>
                <div className="space-y-1">
                  <label className="block text-xs font-medium text-base-content/80">
                    Description (optional)
                  </label>
                  <input
                    type="text"
                    className="input input-sm input-bordered w-full text-xs"
                    placeholder="e.g. Specialized in technical analysis and summaries"
                    value={apiDescription}
                    onChange={(e) => setApiDescription(e.target.value)}
                    aria-label="Description"
                  />
                </div>
                <div className="space-y-1">
                  <label className="block text-xs font-medium text-base-content/80">
                    System Instructions / Prompt
                  </label>
                  <textarea
                    className="textarea textarea-sm textarea-bordered w-full font-mono text-xs"
                    rows={3}
                    placeholder="You are an expert AI assistant..."
                    value={apiPrompt}
                    onChange={(e) => setApiPrompt(e.target.value)}
                    aria-label="System prompt"
                    data-testid="input-api-prompt"
                  />
                </div>
                <AgentWorkspaceBinding
                  kind="api"
                  value={emptyWorkspaceFields()}
                  onChange={() => undefined}
                />
              </>
            ) : null}

            {selectedKind === 'blueprint' ? (
              <>
                <div className="space-y-1">
                  <label className="block text-xs font-medium text-base-content/80">
                    Blueprint Name <span className="text-error">*</span>
                  </label>
                  <input
                    ref={firstInputRef}
                    type="text"
                    className="input input-sm input-bordered w-full"
                    placeholder="e.g. Release Captain"
                    value={bpName}
                    onChange={(e) => setBpName(e.target.value)}
                    required
                    autoFocus
                    aria-label="Blueprint name"
                    data-testid="input-blueprint-name"
                  />
                </div>
                <div className="space-y-1">
                  <label className="block text-xs font-medium text-base-content/80">
                    Description (optional)
                  </label>
                  <input
                    type="text"
                    className="input input-sm input-bordered w-full text-xs"
                    placeholder="e.g. Coordinates releases across services"
                    value={bpDescription}
                    onChange={(e) => setBpDescription(e.target.value)}
                    aria-label="Description"
                  />
                </div>
                <div className="space-y-1">
                  <label className="block text-xs font-medium text-base-content/80">
                    System Instructions / Prompt
                  </label>
                  <textarea
                    className="textarea textarea-sm textarea-bordered w-full font-mono text-xs"
                    rows={3}
                    placeholder="You are a blueprint agent..."
                    value={bpPrompt}
                    onChange={(e) => setBpPrompt(e.target.value)}
                    aria-label="System prompt"
                    data-testid="input-blueprint-prompt"
                  />
                </div>
                <AgentWorkspaceBinding
                  kind="blueprint"
                  value={emptyWorkspaceFields()}
                  onChange={() => undefined}
                />
              </>
            ) : null}

            {selectedKind === 'remote' ? (
              <>
                <div className="space-y-1">
                  <label className="block text-xs font-medium text-base-content/80">
                    Remote Type <span className="text-error">*</span>
                  </label>
                  <select
                    className="select select-sm select-bordered w-full"
                    value={remoteKind}
                    onChange={(e) => setRemoteKind(e.target.value)}
                    aria-label="Remote type"
                    data-testid="select-remote-kind"
                  >
                    {remoteImpls.map((impl) => (
                      <option key={impl.id} value={impl.id}>
                        {impl.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="block text-xs font-medium text-base-content/80">
                    Base URL {remoteKind === 'herdr' ? '(optional — local Herdr)' : <span className="text-error">*</span>}
                  </label>
                  <input
                    ref={firstInputRef}
                    type="url"
                    className="input input-sm input-bordered w-full font-mono text-xs"
                    placeholder="http://localhost:8000"
                    value={remoteBaseUrl}
                    onChange={(e) => setRemoteBaseUrl(e.target.value)}
                    aria-label="Base URL"
                    data-testid="input-remote-url"
                  />
                </div>
                <div className="space-y-1">
                  <label className="block text-xs font-medium text-base-content/80">
                    API Key / Token (optional)
                  </label>
                  <input
                    type="password"
                    className="input input-sm input-bordered w-full text-xs"
                    placeholder="Optional authorization token"
                    value={remoteApiKey}
                    onChange={(e) => setRemoteApiKey(e.target.value)}
                    aria-label="API Key"
                    data-testid="input-remote-key"
                  />
                </div>
                <AgentWorkspaceBinding
                  kind="remote"
                  value={emptyWorkspaceFields()}
                  onChange={() => undefined}
                />
              </>
            ) : null}

            <div className="flex items-center justify-end gap-2 pt-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleCancelForm}
                disabled={submitting}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                size="sm"
                loading={submitting}
                disabled={Boolean(folderError || repoError)}
                data-testid="submit-create-agent"
              >
                {mode === 'edit'
                  ? 'Save Changes'
                  : selectedKind === 'remote' && configuredRemoteRows.length > 0 && !remoteBaseUrl
                  ? 'Connect Selected'
                  : 'Create Agent'}
              </Button>
            </div>
          </form>
        </div>
      </div>
    </Modal>
  )
}
