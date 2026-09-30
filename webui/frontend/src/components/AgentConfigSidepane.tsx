/**
 * #1258 — standalone agent configuration sidepane.
 *
 * #1447: this is the only config surface. Computer Control dropped its Agent
 * tab so Routines stay a schedule surface. This sheet owns seat identity
 * (name, role), routing (provider/model profile), the bound working folder,
 * attached skills, per-agent sandbox opt-in (#719), and — for API seats —
 * the system instruction. Persistence reuses the canonical agent-edit path
 * (`saveAgentEdit`), so the rail, navbar and editors all observe one source
 * of truth through `AGENT_EDITS_CHANGED_EVENT`.
 */
import { useEffect, useMemo, useState } from 'react'
import { apiPatch, fetchLlmProfiles, fetchSkills } from '../lib/api'
import type { AgentRole, LlmProfile, SkillRecord } from '../lib/api'
import { loadAgentEdit, saveAgentEdit } from '../lib/agentEdits'
import { FOLDER_FORMAT_ERROR, isValidFolderPath } from '../lib/agentFolder'
import { Modal } from './DaisyUI'

const ROLE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'default', label: 'Worker (default)' },
  { value: 'support', label: 'support' },
  { value: 'gate', label: 'gate' },
  { value: 'skeptic', label: 'skeptic' },
  { value: 'chief_of_staff', label: 'cos' },
  { value: 'engineer', label: 'engineer' },
  { value: 'suggestions', label: 'suggestions' },
  { value: 'advisor', label: 'advisor' },
]

export interface AgentConfigSidepaneProps {
  agentId: string
  agentName: string
  agentKind?: string | null
  instructions?: string | null
  provider?: string | null
  model?: string | null
  /** Folder picker applies to local-bound seats only (#1257). */
  workspaceEditable?: boolean
  onClose: () => void
}

function profileLabel(profile: LlmProfile): string {
  const name = profile.name || profile.id
  return profile.model ? `${name} · ${profile.model}` : name
}

export function AgentConfigSidepane({
  agentId,
  agentName,
  agentKind = null,
  instructions = null,
  provider = null,
  model = null,
  workspaceEditable = false,
  onClose,
}: AgentConfigSidepaneProps) {
  const isApi = (agentKind ?? 'api') === 'api'
  const isRemote = agentKind === 'remote'

  const [name, setName] = useState(agentName)
  const [role, setRole] = useState<AgentRole>('default')
  const [folder, setFolder] = useState('')
  const [skills, setSkills] = useState<string[]>([])
  const [profileOverride, setProfileOverride] = useState('')
  const [instructionDraft, setInstructionDraft] = useState(instructions || '')
  const [initialInstructions, setInitialInstructions] = useState(instructions || '')
  const [profiles, setProfiles] = useState<LlmProfile[]>([])
  const [skillCatalog, setSkillCatalog] = useState<SkillRecord[]>([])
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // #719 / #1447: per-agent sandbox opt-in lives on config, not Routines.
  const [sandboxChoice, setSandboxChoice] = useState<string>('settings')
  const [initialSandbox, setInitialSandbox] = useState<string>('settings')

  // Hydrate from the canonical edit record whenever the seat changes.
  useEffect(() => {
    const edit = loadAgentEdit(agentId)
    setName(edit.name || agentName)
    setRole((edit.role as AgentRole) || 'default')
    setFolder(edit.folder || '')
    setSkills([...(edit.skills ?? [])])
    setProfileOverride(edit.profileOverride || edit.llmOverride || '')
    setInstructionDraft(instructions || '')
    setInitialInstructions(instructions || '')
    setSandboxChoice('settings')
    setInitialSandbox('settings')
    setError(null)
    setSaved(false)
  }, [agentId, agentName, provider, model, instructions])

  // Catalog fetches run only while the pane is mounted (it mounts on open).
  useEffect(() => {
    let cancelled = false
    void fetchLlmProfiles()
      .then((data) => {
        if (!cancelled) setProfiles(Array.isArray(data?.profiles) ? data.profiles : [])
      })
      .catch(() => {
        if (!cancelled) setProfiles([])
      })
    if (!isRemote) {
      void fetchSkills()
        .then((data) => {
          if (!cancelled) setSkillCatalog(Array.isArray(data?.data) ? data.data : [])
        })
        .catch(() => {
          if (!cancelled) setSkillCatalog([])
        })
    }
    return () => {
      cancelled = true
    }
  }, [isRemote])

  const profileOptions = useMemo(
    () =>
      profiles.filter(
        (profile) =>
          profile.id !== undefined && profile.id !== null && String(profile.id).length > 0,
      ),
    [profiles],
  )

  const reset = () => {
    const edit = loadAgentEdit(agentId)
    setName(edit.name || agentName)
    setRole((edit.role as AgentRole) || 'default')
    setFolder(edit.folder || '')
    setSkills([...(edit.skills ?? [])])
    setProfileOverride(
      edit.profileOverride || edit.llmOverride || '',
    )
    setInstructionDraft(instructions || '')
    setSandboxChoice(initialSandbox)
    setError(null)
  }

  const toggleSkill = (skillName: string) => {
    setSkills((prev) =>
      prev.includes(skillName) ? prev.filter((name) => name !== skillName) : [...prev, skillName],
    )
  }

  const save = async () => {
    if (!agentId || saving) return
    if (folder.trim() && !isValidFolderPath(folder)) {
      setError(FOLDER_FORMAT_ERROR)
      return
    }
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      saveAgentEdit(agentId, {
        name,
        role,
        roleOverridden: true,
        folder,
        skills,
        profileOverride,
      })
      if (isApi) {
        const body: Record<string, unknown> = {}
        if (instructionDraft !== initialInstructions) {
          body.instructions = instructionDraft
        }
        if (sandboxChoice !== initialSandbox) {
          body.sandbox =
            sandboxChoice === 'settings'
              ? { provider: 'none', _clear: true }
              : { provider: sandboxChoice }
        }
        if (Object.keys(body).length > 0) {
          try {
            await apiPatch(`/v1/blueprints/custom/${encodeURIComponent(agentId)}/`, body)
            if (body.instructions !== undefined) setInitialInstructions(instructionDraft)
            if (body.sandbox !== undefined) setInitialSandbox(sandboxChoice)
          } catch {
            /* instruction / sandbox persistence is best-effort; local edits already saved */
          }
        }
      }
      setSaved(true)
      window.setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      isOpen
      onClose={onClose}
      placement="end"
      size="sheet"
      className="flex min-h-0 max-w-sm flex-col"
      aria-label="Agent configuration"
    >
      <div className="flex min-h-0 flex-1 flex-col gap-3" data-testid="agent-config-sidepane">
        <header className="flex items-center gap-2">
          <div className="min-w-0 flex-1">
            <h2
              className="truncate text-base font-semibold"
              data-testid="agent-config-name-heading"
            >
              {name || agentName}
            </h2>
            {agentKind ? (
              <span className="badge badge-sm badge-ghost mt-0.5" data-testid="agent-config-kind">
                {agentKind}
              </span>
            ) : null}
          </div>
        </header>

        <label className="form-control block">
          <span className="mb-1 block text-sm font-medium">Agent name</span>
          <input
            type="text"
            className="input input-sm input-bordered w-full"
            aria-label="Agent name"
            data-testid="agent-config-name-input"
            value={name}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                void save()
              }
            }}
            onFocus={(event) => event.stopPropagation()}
            onPaste={(event) => event.stopPropagation()}
          />
        </label>

        <label className="form-control block">
          <span className="mb-1 block text-sm font-medium">Role</span>
          <select
            className="select select-sm select-bordered w-full"
            aria-label="Role"
            data-testid="agent-config-role"
            value={role}
            onChange={(event) => setRole(event.target.value as AgentRole)}
          >
            {ROLE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        {isApi ? (
          <label className="form-control block">
            <span className="mb-1 block text-sm font-medium">Provider / model</span>
            <select
              className="select select-sm select-bordered w-full"
              aria-label="Provider and model"
              data-testid="agent-config-profile"
              value={profileOverride}
              onChange={(event) => setProfileOverride(event.target.value)}
            >
              <option value="">Use default inference</option>
              {profileOptions.map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profileLabel(profile)}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-base-content/60">
              Provider and model follow the selected inference profile.
              {provider || model
                ? ` Currently: ${[provider, model].filter(Boolean).join('/')}.`
                : ''}
            </p>
          </label>
        ) : null}

        {workspaceEditable ? (
          <label className="form-control block">
            <span className="mb-1 block text-sm font-medium">Working folder</span>
            <input
              type="text"
              className="input input-sm input-bordered w-full"
              aria-label="Working folder"
              data-testid="agent-config-folder"
              placeholder="/path/to/project"
              value={folder}
              onChange={(event) => setFolder(event.target.value)}
              onFocus={(event) => event.stopPropagation()}
              onPaste={(event) => event.stopPropagation()}
            />
          </label>
        ) : null}

        {!isRemote ? (
          <fieldset className="form-control" data-testid="agent-config-skills">
            <legend className="mb-1 text-sm font-medium">Skills</legend>
            {skillCatalog.length === 0 ? (
              <p className="text-xs text-base-content/60">No skills available.</p>
            ) : (
              <div className="max-h-40 space-y-1 overflow-auto rounded-box border border-base-300 p-2">
                {skillCatalog.map((skill) => (
                  <label
                    key={skill.name}
                    className="flex cursor-pointer items-center gap-2 text-sm"
                  >
                    <input
                      type="checkbox"
                      className="checkbox checkbox-sm"
                      checked={skills.includes(skill.name)}
                      onChange={() => toggleSkill(skill.name)}
                    />
                    <span className="truncate">{skill.name}</span>
                  </label>
                ))}
              </div>
            )}
          </fieldset>
        ) : null}

        {isApi ? (
          <label className="form-control block">
            <span className="mb-1 block text-sm font-medium">System instruction</span>
            <textarea
              className="textarea textarea-bordered w-full text-sm"
              rows={5}
              aria-label="System instruction"
              data-testid="agent-config-instructions"
              value={instructionDraft}
              onChange={(event) => setInstructionDraft(event.target.value)}
              onFocus={(event) => event.stopPropagation()}
              onPaste={(event) => event.stopPropagation()}
            />
          </label>
        ) : null}

        {isApi ? (
          <label className="form-control block">
            <span className="mb-1 block text-sm font-medium">Sandbox tools</span>
            <select
              className="select select-sm select-bordered w-full"
              aria-label="Sandbox tools"
              data-testid="sandbox-opt-in"
              value={sandboxChoice}
              onChange={(event) => setSandboxChoice(event.target.value)}
            >
              <option value="settings">Follow global Settings</option>
              <option value="daytona">Daytona (opt in)</option>
              <option value="none">None (opt out)</option>
            </select>
            <span className="mt-1 block text-[11px] text-base-content/50">
              Opt in attaches code/file tools to this agent alone; the global
              provider stays untouched.
            </span>
          </label>
        ) : null}

        {error ? (
          <p className="text-sm text-error" role="alert">
            {error}
          </p>
        ) : null}

        <div className="mt-auto flex items-center gap-2">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            data-testid="agent-config-save"
            disabled={saving}
            onClick={() => void save()}
          >
            {saving ? 'Saving…' : saved ? 'Saved' : 'Save changes'}
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            data-testid="agent-config-reset"
            onClick={reset}
          >
            Reset
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            data-testid="agent-config-cancel"
            onClick={onClose}
          >
            Cancel
          </button>
        </div>
      </div>
    </Modal>
  )
}

export default AgentConfigSidepane
