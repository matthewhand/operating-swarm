import { useEffect, useId, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Input, Modal, Select, Textarea, useToast } from './DaisyUI'
import LlmProfileAddForm from './LlmProfileAddForm'
import InferenceOrderList, { type InferenceCatalogOption } from './InferenceOrderList'
import {
  fetchBlueprints,
  fetchSkills,
  fetchCliAgents,
  fetchCliModels,
  fetchLlmProfiles,
  fetchImageGenSettings,
  fetchRemotes,
  generateAgentAvatar,
  type AgentRole,
  type Blueprint,
} from '../lib/api'
import { RemoteSelect } from './RemoteSelect'
import { configuredRemotes } from '../lib/remotes'
import {
  loadAgentRemoteBinding,
  remotesListForSelect,
  saveAgentRemoteBinding,
} from '../lib/agentRemote'
import {
  assignedBlueprintId,
  loadAgentEdit,
  loadInferenceList,
  saveAgentEdit,
  saveInferenceList,
} from '../lib/agentEdits'
import { apiModelOptionsFromProfiles } from '../lib/cliAgentContext'
import { FOLDER_FORMAT_ERROR, isValidFolderPath } from '../lib/agentFolder'
import {
  GITHUB_REPO_FORMAT_ERROR,
  emptyWorkspaceFields,
  isValidGithubRepo,
  type AgentWorkspaceFields,
} from '../lib/agentWorkspace'
import AgentWorkspaceBinding from './AgentWorkspaceBinding'
import type { InferenceSeat } from '../lib/inferenceList'
import {
  NEW_CHAT_PER_TASK_LABEL,
  NEW_CHAT_PER_TASK_TOOLTIP,
  USE_SUGGESTIONS_LABEL,
  USE_SUGGESTIONS_TOOLTIP,
  fetchAgentSettings,
  saveAgentSettings,
} from '../lib/agentSettings'
import {
  agentRole,
  applyBlueprintAssignment,
  assignableBlueprints,
  catalogPickerLabel,
  exampleRoleAgents,
} from '../lib/agentRoles'
import { displayNameMatchesBlueprint } from '../lib/railSeats'
import { ROLE_BRIEFS } from '../lib/definitionExplain'
import { agentLabel, sessionKindForAgent } from '../lib/supportAgent'
import { isCliBlueprintId } from '../lib/cliAgentContext'
import { rememberGeneratedAvatar } from '../lib/agentAvatars'
import { defaultAvatarPrompt, isImageGenConfigured, parseImageGenSettings } from '../lib/imageGenSettings'
import AgentAvatar from './AgentAvatar'
import { openSettingsSheet } from './SettingsSheet'
import MailboxAclEditor from './MailboxAclEditor'

/** Window event so the rail hover-edit and tests can open the agent editor. */
export const OPEN_AGENT_EDITOR_EVENT = 'swarm:open-agent-editor'

export interface OpenAgentEditorDetail {
  agentId: string
}

export function openAgentEditor(detail: OpenAgentEditorDetail): void {
  window.dispatchEvent(
    new CustomEvent<OpenAgentEditorDetail>(OPEN_AGENT_EDITOR_EVENT, { detail }),
  )
}

const ROLE_OPTIONS: { value: AgentRole; label: string }[] = [
  { value: 'default', label: 'none' },
  { value: 'support', label: 'support' },
  { value: 'gate', label: 'gate' },
  { value: 'skeptic', label: 'skeptic' },
  { value: 'chief_of_staff', label: 'cos' },
  { value: 'engineer', label: 'engineer' },
  { value: 'suggestions', label: 'suggestions' },
]

const EMPTY_BLUEPRINTS: Blueprint[] = []

export interface AgentEditorProps {
  isOpen: boolean
  onClose: () => void
  agentId: string | null
}

/**
 * Agent-scoped editor overlay (REQ-58 / REQ-124).
 *
 * Name, role with explanation, which catalog blueprint this seat uses,
 * kind-appropriate LLM override (disabled for remotes, CLI->model for CLIs,
 * profile->model for API).
 */
export default function AgentEditor({ isOpen, onClose, agentId }: AgentEditorProps) {
  const id = agentId || ''
  const toggleId = useId()
  const suggestionsToggleId = useId()
  const { success, error: toastError } = useToast()
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [role, setRole] = useState<AgentRole>('default')
  const [blueprintId, setBlueprintId] = useState('')
  const [llmOverride, setLlmOverride] = useState('')
  const [cliOverride, setCliOverride] = useState('')
  const [profileOverride, setProfileOverride] = useState('')
  const [newChatPerTask, setNewChatPerTask] = useState(false)
  const [useSuggestions, setUseSuggestions] = useState(false)
  const [savingSettings, setSavingSettings] = useState(false)
  const [boundRemoteId, setBoundRemoteId] = useState('')
  const [inferenceSeats, setInferenceSeats] = useState<InferenceSeat[]>([])
  const [avatarPrompt, setAvatarPrompt] = useState('')
  const [folder, setFolder] = useState('')
  const [folderError, setFolderError] = useState<string | null>(null)
  const [githubRepo, setGithubRepo] = useState('')
  const [repoError, setRepoError] = useState<string | null>(null)
  const [attachedSkills, setAttachedSkills] = useState<string[]>([])
  const [addingProfile, setAddingProfile] = useState(false)

  const blueprintsQuery = useQuery({
    queryKey: ['blueprints'],
    queryFn: fetchBlueprints,
    enabled: isOpen,
    retry: 1,
  })

  const catalog = useMemo(
    () => assignableBlueprints(exampleRoleAgents(blueprintsQuery.data?.data ?? EMPTY_BLUEPRINTS)),
    [blueprintsQuery.data],
  )
  const agent = catalog.find((item) => item.id === id)
  const catalogName = agent ? agentLabel({ id: agent.id, name: agent.name }) : id
  const title = id ? `Edit ${catalogName}` : 'Edit agent'

  const agentKind = useMemo(() => {
    if (!id) return 'api'
    const lowerId = id.toLowerCase()
    if (lowerId.startsWith('remote-') || agent?.tags?.includes('remote') || lowerId.includes('remote')) {
      return 'remote'
    }
    if (
      lowerId.startsWith('cli-') ||
      isCliBlueprintId(id) ||
      agent?.tags?.includes('cli') ||
      lowerId.includes('cli')
    ) {
      return 'cli'
    }
    return sessionKindForAgent({ id, tags: agent?.tags })
  }, [id, agent])

  const cliQuery = useQuery({
    queryKey: ['cli-agents'],
    queryFn: fetchCliAgents,
    enabled: isOpen,
    retry: 1,
  })

  const activeCli = cliOverride || cliQuery.data?.clis?.[0] || ''

  const cliModelsQuery = useQuery({
    queryKey: ['cli-models', activeCli],
    queryFn: () => (activeCli ? fetchCliModels(activeCli) : Promise.resolve({ cli: '', models: [] })),
    enabled: Boolean(isOpen && agentKind === 'cli' && activeCli),
    retry: 1,
  })

  const skillsQuery = useQuery({
    queryKey: ['skills'],
    queryFn: fetchSkills,
    enabled: isOpen && agentKind !== 'remote',
    retry: 1,
  })

  const llmProfilesQuery = useQuery({
    queryKey: ['llm-profiles'],
    queryFn: fetchLlmProfiles,
    enabled: isOpen,
    retry: 1,
  })

  const remotesQuery = useQuery({
    queryKey: ['remotes-list'],
    queryFn: fetchRemotes,
    enabled: isOpen,
    retry: 1,
  })

  const imageGenQuery = useQuery({
    queryKey: ['image-gen-settings'],
    queryFn: () => fetchImageGenSettings(false),
    enabled: isOpen,
    retry: 1,
  })
  const imageGen = parseImageGenSettings(imageGenQuery.data)
  const canGenerateAvatar = isImageGenConfigured(imageGen)
  const remotesCatalog = remotesListForSelect(
    remotesQuery.data,
    null,
    boundRemoteId ? loadAgentRemoteBinding(id) : null,
  )
  const configuredRemoteRows = configuredRemotes(remotesCatalog)

  const catalogAgentIds = useMemo(
    () => new Set(catalog.map((item) => item.id.toLowerCase())),
    [catalog],
  )

  const availableClis = useMemo(() => {
    return (cliQuery.data?.clis ?? []).filter((c) => !catalogAgentIds.has(c.toLowerCase()))
  }, [cliQuery.data, catalogAgentIds])

  const availableCliModels = useMemo(() => {
    return (cliModelsQuery.data?.models ?? []).filter((m) => !catalogAgentIds.has(m.toLowerCase()))
  }, [cliModelsQuery.data, catalogAgentIds])

  const availableApiModels = useMemo(() => {
    return apiModelOptionsFromProfiles(llmProfilesQuery.data?.profiles, [
      llmProfilesQuery.data?.default_llm_profile ?? '',
    ]).filter((row) => !catalogAgentIds.has(row.id.toLowerCase()))
  }, [llmProfilesQuery.data, catalogAgentIds])

  useEffect(() => {
    if (!isOpen || !id) return
    const edit = loadAgentEdit(id)
    const catalogAgent = exampleRoleAgents(blueprintsQuery.data?.data ?? []).find(
      (item) => item.id === id,
    )
    setName(edit.name || catalogAgent?.name || id)
    setRole(edit.role || agentRole({ id, name: catalogAgent?.name, role: catalogAgent?.role }))
    setBlueprintId(edit.blueprintId || id)
    setLlmOverride(edit.llmOverride || '')
    setCliOverride(edit.cliOverride || '')
    setProfileOverride(edit.profileOverride || '')
    setBoundRemoteId(loadAgentRemoteBinding(id)?.id || '')
    setInferenceSeats(loadInferenceList(id))
    setFolder(edit.folder || '')
    setFolderError(null)
    setGithubRepo(edit.githubRepo || '')
    setRepoError(null)
    setAttachedSkills(edit.skills || [])
    const catalogNameForPrompt = catalogAgent?.name || id
    const roleForPrompt = edit.role || agentRole({ id, name: catalogAgent?.name, role: catalogAgent?.role })
    setAvatarPrompt(defaultAvatarPrompt(edit.name || catalogNameForPrompt, roleForPrompt))

    let cancelled = false
    ;(async () => {
      const settings = await fetchAgentSettings(id)
      if (!cancelled) {
        setNewChatPerTask(settings.new_chat_per_task)
        setUseSuggestions(settings.use_suggestions)
        if (!edit.folder && settings.folder) {
          setFolder(settings.folder)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [isOpen, id, blueprintsQuery.data])

  const handleToggleNewChat = async (next: boolean) => {
    setNewChatPerTask(next)
    if (!id) return
    setSavingSettings(true)
    try {
      await saveAgentSettings(id, { new_chat_per_task: next })
    } finally {
      setSavingSettings(false)
    }
  }

  const handleToggleSuggestions = async (next: boolean) => {
    setUseSuggestions(next)
    if (!id) return
    setSavingSettings(true)
    try {
      await saveAgentSettings(id, { use_suggestions: next })
    } finally {
      setSavingSettings(false)
    }
  }

  const persistBlueprint = (nextId: string) => {
    setBlueprintId(nextId)
    const picked = catalog.find((item) => item.id === nextId)
    const next = applyBlueprintAssignment(id, {
      id: nextId,
      role: picked?.role,
      workflow: picked?.workflow,
    })
    if (!next.roleOverridden) {
      setRole(next.role || 'default')
    }
  }

  const persistName = (next: string) => {
    setName(next)
    saveAgentEdit(id, { name: next })
  }

  const persistRole = (next: AgentRole) => {
    setRole(next)
    saveAgentEdit(id, { role: next, roleOverridden: true })
    setAvatarPrompt((current) => {
      const derived = defaultAvatarPrompt(name || catalogName, next)
      if (!current.trim() || current === defaultAvatarPrompt(name || catalogName, role)) {
        return derived
      }
      return current
    })
  }

  const generateAvatar = useMutation({
    mutationFn: () =>
      generateAgentAvatar(id, {
        prompt: avatarPrompt.trim() || defaultAvatarPrompt(name || catalogName, role),
        name: name || catalogName,
        role,
      }),
    onSuccess: (result) => {
      rememberGeneratedAvatar(id, result.avatar_path)
      void queryClient.invalidateQueries({ queryKey: ['image-gen-settings'] })
      void queryClient.invalidateQueries({ queryKey: ['blueprints'] })
      success('Avatar generated', 'Still image stored for this agent.')
    },
    onError: (err: Error) => {
      toastError('Could not generate avatar', err.message)
    },
  })

  const openImageGenSettings = () => {
    onClose()
    openSettingsSheet({ section: 'image-gen' })
  }

  const persistInference = (next: InferenceSeat[]) => {
    setInferenceSeats(next)
    saveInferenceList(id, next)
  }

  const inferenceCatalog = useMemo<InferenceCatalogOption[]>(() => {
    const rows: InferenceCatalogOption[] = []
    const profiles = llmProfilesQuery.data?.profiles ?? []
    if (profiles.length) {
      for (const p of profiles) {
        rows.push({ id: p.id, kind: 'llm', label: p.name || p.id })
      }
    } else {
      for (const id of ['orchestration', 'auxiliary', 'delegation']) {
        rows.push({ id, kind: 'llm', label: id })
      }
    }
    for (const cli of cliQuery.data?.clis ?? []) {
      rows.push({ id: cli, kind: 'cli', label: cli })
    }
    for (const remote of configuredRemoteRows) {
      rows.push({
        id: remote.id,
        kind: 'remote',
        label: remote.label || remote.id,
      })
    }
    return rows
  }, [llmProfilesQuery.data, cliQuery.data, configuredRemoteRows])

  const defaultInferenceLabel =
    llmProfilesQuery.data?.default_llm_profile || 'orchestration'

  const openBlueprintInSettings = () => {
    const assigned = assignedBlueprintId(id) || blueprintId || id
    onClose()
    openSettingsSheet({ section: 'blueprint', blueprintId: assigned })
  }

  const recipeId = blueprintId || id
  const assignedRecipe = catalog.find((item) => item.id === recipeId)
  const nameMatchesRecipe = displayNameMatchesBlueprint(
    name,
    recipeId,
    assignedRecipe?.name,
  )

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={title}
      placement="end"
      size="lg"
      className="flex min-h-0 flex-col"
    >
      <div
        id="os-agent-editor"
        className="space-y-4 max-h-[calc(100vh-12rem)] overflow-y-auto pr-1"
        data-agent-id={id || undefined}
      >
        <p className="text-sm text-base-content/70">
          This pane is only about this agent. Blueprint picks a catalog recipe
          for this seat — it is not Settings.
        </p>

        <Input
          label="Name"
          name="agent-name"
          value={name}
          onChange={(event) => persistName(event.target.value)}
          autoComplete="off"
          spellCheck={false}
        />

        <div className="form-control">
          <Select
            label="Role"
            name="agent-role"
            value={role}
            onChange={(event) => persistRole(event.target.value as AgentRole)}
          >
            {ROLE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
          <p className="text-xs text-base-content/70 mt-1" data-testid="role-explanation">
            {ROLE_BRIEFS[role] || ROLE_BRIEFS.default}
          </p>
          <p className="text-xs text-base-content/55 mt-1" data-testid="role-override-rule">
            Changing Role here wins over the blueprint default. Re-picking a
            blueprint restores that recipe&apos;s role unless you have overridden
            it.
          </p>
        </div>

        {id ? <MailboxAclEditor agentId={id} role={role} /> : null}

        <div className="space-y-1">
          <Select
            label={nameMatchesRecipe ? undefined : 'Blueprint'}
            aria-label="Blueprint"
            name="agent-blueprint"
            value={blueprintId}
            onChange={(event) => persistBlueprint(event.target.value)}
          >
            {catalog.length === 0 || !catalog.some((item) => item.id === recipeId) ? (
              <option value={recipeId}>{recipeId || 'Loading…'}</option>
            ) : null}
            {catalog.map((item) => (
              <option key={item.id} value={item.id}>
                {catalogPickerLabel(item)}
              </option>
            ))}
          </Select>
          {nameMatchesRecipe ? (
            <p
              className="text-xs text-base-content/60"
              data-testid="blueprint-recipe-meta"
            >
              Recipe: {recipeId}
            </p>
          ) : null}
        </div>

        <InferenceOrderList
          seats={inferenceSeats}
          catalog={inferenceCatalog}
          defaultLabel={defaultInferenceLabel}
          onChange={persistInference}
        />

        {agentKind !== 'remote' ? (
          <div className="space-y-2" data-testid="agent-editor-skills">
            <span className="text-sm font-semibold text-base-content/80">Skills</span>
            <p className="text-xs text-base-content/60">
              Attach one or more SKILL.md capabilities discovered under skills/.
              Today&apos;s API seats are Blueprint-backed (ADR-006); true
              inference-only API seats do not attach skills until that kind
              exists.
            </p>
            {(skillsQuery.data?.data ?? []).length === 0 ? (
              <p className="text-xs text-base-content/55">No discoverable skills.</p>
            ) : (
              <ul className="space-y-1">
                {(skillsQuery.data?.data ?? []).map((skill) => {
                  const checked = attachedSkills.includes(skill.name)
                  return (
                    <li key={skill.name}>
                      <label className="flex items-start gap-2 text-sm">
                        <input
                          type="checkbox"
                          className="checkbox checkbox-sm mt-0.5"
                          data-testid={`agent-skill-${skill.name}`}
                          checked={checked}
                          onChange={() => {
                            const next = checked
                              ? attachedSkills.filter((name) => name !== skill.name)
                              : [...attachedSkills, skill.name]
                            setAttachedSkills(next)
                            saveAgentEdit(id, { skills: next })
                          }}
                        />
                        <span>
                          <span className="font-medium">{skill.name}</span>
                          {skill.description ? (
                            <span className="block text-xs text-base-content/60">
                              {skill.description}
                            </span>
                          ) : null}
                        </span>
                      </label>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        ) : null}

        <div
          className="space-y-3 rounded-box border border-base-300 bg-base-200/40 p-3"
          data-testid="agent-editor-avatar"
        >
          <div className="flex items-start gap-3">
            <AgentAvatar
              agentId={id}
              alt=""
              size="lg"
              className="shrink-0"
            />
            <div className="min-w-0 flex-1">
              <span className="text-sm font-semibold text-base-content/80">Still avatar</span>
              <p className="text-xs text-base-content/60 mt-0.5">
                Generated stills apply on Bland. Blobs with eyes stay a separate
                Rail theme and ignore generated stills.
              </p>
            </div>
          </div>
          <Textarea
            label="Avatar prompt"
            name="agent-avatar-prompt"
            value={avatarPrompt}
            onChange={(event) => setAvatarPrompt(event.target.value)}
            rows={3}
            spellCheck={false}
          />
          {canGenerateAvatar ? (
            <Button
              type="button"
              variant="primary"
              size="sm"
              disabled={!id || generateAvatar.isPending}
              onClick={() => generateAvatar.mutate()}
            >
              {generateAvatar.isPending ? 'Generating…' : 'Generate avatar'}
            </Button>
          ) : (
            <div className="space-y-2">
              <Button type="button" variant="primary" size="sm" disabled>
                Generate avatar
              </Button>
              <p className="text-xs text-base-content/60" data-testid="generate-avatar-disabled-hint">
                Set a base URL in{' '}
                <button
                  type="button"
                  className="link link-hover font-medium"
                  onClick={openImageGenSettings}
                >
                  Settings → Image generation
                </button>{' '}
                first. Empty/off does not guess a host.
              </p>
            </div>
          )}
        </div>

        {/* LLM Override Picker by Kind (REQ-124) */}
        {agentKind === 'remote' && (
          <div className="space-y-3">
            {configuredRemoteRows.length === 0 ? (
              <div className="rounded-box border border-base-300 bg-base-200/40 p-3">
                <span className="text-sm font-semibold">Remote</span>
                <p className="text-xs text-base-content/60 mt-1">
                  Add a remote before this agent is usable.
                </p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="mt-2"
                  onClick={() => {
                    onClose()
                    openSettingsSheet({ section: 'remotes', addRemote: true })
                  }}
                >
                  Add remote
                </Button>
              </div>
            ) : (
              <RemoteSelect
                remotes={remotesCatalog}
                value={boundRemoteId}
                onChange={(nextId) => {
                  setBoundRemoteId(nextId)
                  const remote = configuredRemoteRows.find((row) => row.id === nextId)
                  saveAgentRemoteBinding(
                    id,
                    remote ? { id: remote.id, kind: remote.kind || remote.id } : null,
                  )
                }}
                label="Remote"
              />
            )}
            <div className="rounded-box border border-base-300 bg-base-200/40 p-3 opacity-60">
              <span className="text-sm font-semibold text-base-content/70">LLM override</span>
              <p className="text-xs text-base-content/60 mt-1">Remotes keep their own models</p>
            </div>
          </div>
        )}

        {agentKind === 'cli' && (
          <div className="space-y-3 rounded-box border border-base-300 bg-base-200/40 p-3">
            <div>
              <span className="text-sm font-semibold text-base-content/80">LLM override</span>
              <p className="text-xs text-base-content/60 mt-0.5" data-testid="default-llm-label">
                Default would be: {availableClis[0] || 'CLI default'} / {availableCliModels[0] || 'none'}
              </p>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="form-control">
                <label className="label py-1">
                  <span className="label-text text-xs">CLI</span>
                </label>
                <select
                  aria-label="CLI override"
                  className="select select-bordered select-sm w-full"
                  value={cliOverride}
                  onChange={(e) => {
                    const nextCli = e.target.value
                    setCliOverride(nextCli)
                    saveAgentEdit(id, { cliOverride: nextCli, llmOverride })
                  }}
                >
                  <option value="">Default CLI</option>
                  {availableClis.map((cli) => (
                    <option key={cli} value={cli}>
                      {cli}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-control">
                <label className="label py-1">
                  <span className="label-text text-xs">Model</span>
                </label>
                <select
                  aria-label="Model override"
                  className="select select-bordered select-sm w-full"
                  value={llmOverride}
                  onChange={(e) => {
                    const nextModel = e.target.value
                    setLlmOverride(nextModel)
                    saveAgentEdit(id, { cliOverride, llmOverride: nextModel })
                  }}
                >
                  <option value="">Default model</option>
                  {availableCliModels.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        )}

        {agentKind === 'api' && (
          <div className="space-y-3 rounded-box border border-base-300 bg-base-200/40 p-3">
            <div>
              <span className="text-sm font-semibold text-base-content/80">LLM override</span>
              <p className="text-xs text-base-content/60 mt-0.5" data-testid="default-llm-label">
                Default would be:{' '}
                {llmProfilesQuery.data?.default_llm_profile || 'orchestration'}
                {availableApiModels.length > 0 ? ` / ${availableApiModels[0].label}` : ''}
              </p>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="form-control">
                <label className="label py-1">
                  <span className="label-text text-xs">API / LLM profile</span>
                </label>
                <select
                  aria-label="API profile override"
                  className="select select-bordered select-sm w-full"
                  value={profileOverride}
                  onChange={(e) => {
                    const nextProfile = e.target.value
                    setProfileOverride(nextProfile)
                    saveAgentEdit(id, { profileOverride: nextProfile, llmOverride })
                  }}
                >
                  <option value="">Default profile</option>
                  <option value="orchestration">User chat / orchestration</option>
                  <option value="auxiliary">Auxiliary (code summary)</option>
                  <option value="delegation">Delegation (design / coding)</option>
                  {(llmProfilesQuery.data?.profiles ?? [])
                    .filter((p) => !['orchestration', 'auxiliary', 'delegation'].includes(p.id))
                    .map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name || p.id}
                      </option>
                    ))}
                </select>
              </div>

              <div className="form-control">
                <label className="label py-1">
                  <span className="label-text text-xs">Model</span>
                </label>
                <select
                  aria-label="Model override"
                  className="select select-bordered select-sm w-full"
                  value={llmOverride}
                  onChange={(e) => {
                    const nextModel = e.target.value
                    setLlmOverride(nextModel)
                    saveAgentEdit(id, { profileOverride, llmOverride: nextModel })
                  }}
                >
                  <option value="">Default model</option>
                  {availableApiModels.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {addingProfile ? (
              <LlmProfileAddForm
                className="space-y-3 rounded-box border border-base-300 bg-base-100 p-3"
                onCancel={() => setAddingProfile(false)}
                onSaved={async () => {
                  setAddingProfile(false)
                  await llmProfilesQuery.refetch()
                }}
              />
            ) : (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setAddingProfile(true)}
              >
                Add LLM profile
              </Button>
            )}
          </div>
        )}

        <AgentWorkspaceBinding
          kind={agentKind === 'cli' || agentKind === 'remote' ? agentKind : 'api'}
          value={
            agentKind === 'cli'
              ? { folder, githubRepo, workspacesEnabled: false }
              : emptyWorkspaceFields()
          }
          folderError={folderError}
          repoError={repoError}
          onChange={(next: AgentWorkspaceFields) => {
            if (agentKind !== 'cli' || !id) return
            setFolder(next.folder)
            setGithubRepo(next.githubRepo)
            if (next.folder && !isValidFolderPath(next.folder)) {
              setFolderError(FOLDER_FORMAT_ERROR)
              return
            }
            setFolderError(null)
            if (next.githubRepo && !isValidGithubRepo(next.githubRepo)) {
              setRepoError(GITHUB_REPO_FORMAT_ERROR)
              saveAgentEdit(id, { folder: next.folder, githubRepo: next.githubRepo, workspacesEnabled: false })
              return
            }
            setRepoError(null)
            saveAgentEdit(id, {
              folder: next.folder,
              githubRepo: next.githubRepo,
              workspacesEnabled: false,
            })
            void saveAgentSettings(id, { folder: next.folder.trim() })
          }}
        />

        <div
          className="tooltip tooltip-bottom w-full text-left"
          data-tip={NEW_CHAT_PER_TASK_TOOLTIP}
        >
          <label
            htmlFor={toggleId}
            className="label cursor-pointer items-center justify-between gap-4 rounded-box border border-base-300 bg-base-200/60 px-4 py-3"
          >
            <span className="label-text text-base font-semibold">{NEW_CHAT_PER_TASK_LABEL}</span>
            <input
              id={toggleId}
              type="checkbox"
              className="toggle toggle-primary"
              role="switch"
              aria-label={NEW_CHAT_PER_TASK_LABEL}
              checked={newChatPerTask}
              disabled={!id || savingSettings}
              onChange={(event) => handleToggleNewChat(event.target.checked)}
            />
          </label>
        </div>

        <div
          className="tooltip tooltip-bottom w-full text-left"
          data-tip={USE_SUGGESTIONS_TOOLTIP}
        >
          <label
            htmlFor={suggestionsToggleId}
            className="label cursor-pointer items-center justify-between gap-4 rounded-box border border-base-300 bg-base-200/60 px-4 py-3"
          >
            <span className="label-text text-base font-semibold">{USE_SUGGESTIONS_LABEL}</span>
            <input
              id={suggestionsToggleId}
              type="checkbox"
              className="toggle toggle-primary"
              role="switch"
              aria-label={USE_SUGGESTIONS_LABEL}
              checked={useSuggestions}
              disabled={!id || savingSettings}
              onChange={(event) => handleToggleSuggestions(event.target.checked)}
            />
          </label>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={!id}
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
