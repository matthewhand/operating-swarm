/** #856 slice B — LlmProfilesPane (moved verbatim from SettingsSheet.tsx). */
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle, ChevronDown, Server, X } from 'lucide-react'
import { Alert, Button, Select, useToast } from '../.././DaisyUI'
import LlmProfileAddForm from '../.././LlmProfileAddForm'
import EnvOverrideBadge from '../.././EnvOverrideBadge'
import ProviderRateLimitFields from '../.././ProviderRateLimitFields'
import {
  fetchLlmProfiles,
  patchLlmProfiles,
  type LlmTaskClass,
} from '../../../lib/api'
import {
  TASK_CLASS_LABELS,
  missingProfileWarning,
  uiStatusWarnings,
} from '../../../lib/llmProfiles'
import { OVERLAY_CHROME_CLASSES } from '../../../lib/chromeOverlay'

export function LlmProfilesPane({
  focusProviderId = null,
}: {
  focusProviderId?: string | null
}) {
  const { success, error: toastError } = useToast()
  const profilesQuery = useQuery({
    queryKey: ['llm-profiles'],
    queryFn: fetchLlmProfiles,
    retry: 1,
  })
  const remote = profilesQuery.data
  const [defaultId, setDefaultId] = useState('')
  const [overrideOn, setOverrideOn] = useState(false)
  const [overridePopupOpen, setOverridePopupOpen] = useState(false)
  // #575: the truth test for the boolean lives in the same data as the popup
  // rows, so the two cannot drift. A kind gains override support by flipping
  // `enabled` here (or, later, by its kind base declaring it) — the popup and
  // the flag update together, with no second list anywhere in the UI.
  const overrideTaskKinds = useMemo(
    () => [
      {
        id: 'api',
        label: 'API agents',
        enabled: true,
        reason: 'Per-task profile overrides (orchestration / auxiliary / delegation)',
        unavailableReason: '',
      },
      {
        id: 'cli',
        label: 'CLI agents',
        enabled: false,
        reason: 'The CLI owns its own model selection for the session',
        unavailableReason: 'Overrides are API-only for now — the CLI owns its own model selection',
      },
      {
        id: 'remote',
        label: 'Remote agents',
        enabled: false,
        reason: 'The remote provider exposes its own model picker',
        unavailableReason: 'Overrides are API-only for now — the remote provider picks its own models',
      },
    ],
    [],
  )
  const [taskMap, setTaskMap] = useState<Partial<Record<LlmTaskClass, string>>>({})
  const [saving, setSaving] = useState(false)
  const [addingProfile, setAddingProfile] = useState(false)

  const resetAddForm = () => {
    setAddingProfile(false)
  }
  const hydrated = useRef(false)
  const defaultBadge = remote?.provenance?.default_llm_profile
  const defaultForced = Boolean(defaultBadge?.forced)

  useEffect(() => {
    if (!remote || hydrated.current) return
    hydrated.current = true
    setDefaultId(remote.default_llm_profile || '')
    setOverrideOn(Boolean(remote.override_per_task))
    setTaskMap({ ...remote.task_llm_profiles })
  }, [remote])

  const profiles = remote?.profiles ?? []
  const ids = profiles.map((profile) => profile.id)
  const fallback = defaultId || remote?.default_llm_profile || 'default'
  const warnings = uiStatusWarnings(
    [
      ...(remote?.warnings ?? []),
      missingProfileWarning(defaultId, remote, fallback),
      ...((['orchestration', 'auxiliary', 'delegation'] as const).map((cls) =>
        overrideOn ? missingProfileWarning(taskMap[cls], remote, fallback) : null,
      )),
    ].filter((text): text is string => Boolean(text)),
  )

  const optionIds = Array.from(
    new Set(
      [
        ...ids,
        defaultId,
        ...Object.values(taskMap),
      ].filter((id): id is string => Boolean(id)),
    ),
  )

  const handleSave = async (event: FormEvent) => {
    event.preventDefault()
    if (profilesQuery.isError || profiles.length === 0) {
      return
    }
    setSaving(true)
    try {
      const payload: {
        default_llm_profile?: string
        override_per_task: boolean
        task_llm_profiles: Partial<Record<LlmTaskClass, string>>
      } = {
        override_per_task: overrideOn,
        task_llm_profiles: overrideOn
          ? {
              orchestration: taskMap.orchestration || defaultId,
              auxiliary: taskMap.auxiliary || defaultId,
              delegation: taskMap.delegation || defaultId,
            }
          : taskMap,
      }
      if (defaultId.trim()) {
        payload.default_llm_profile = defaultId.trim()
      }
      const saved = await patchLlmProfiles(payload)
      setDefaultId(saved.default_llm_profile || defaultId)
      setOverrideOn(Boolean(saved.override_per_task))
      setTaskMap({ ...saved.task_llm_profiles })
      success('LLM profiles saved', 'Default stored in settings.default_llm_profile.')
    } catch (err) {
      toastError(
        'Could not save LLM profiles',
        err instanceof Error ? err.message : 'Request failed.',
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="space-y-4" onSubmit={handleSave}>
      <div>
        <h4 className="text-lg font-semibold">LLM profiles</h4>
        <p className="text-sm text-base-content/70">
          Pick a Default from any connected CLI, API, or remote. Task-class
          names (orchestration / auxiliary / delegation) are roles, not required
          model ids. Auto-picks fill the map until you change them.
        </p>
      </div>

      {profilesQuery.isPending ? (
        <p className="text-sm text-base-content/60">Loading profiles…</p>
      ) : profilesQuery.isError ? (
        <Alert type="warning" icon={<AlertCircle className="h-5 w-5" />}>
          <span className="text-sm">
            Could not load configured profiles. Chat still uses the server
            default when one is stored.
          </span>
        </Alert>
      ) : profiles.length === 0 ? (
        <Alert type="info" icon={<Server className="h-5 w-5" />}>
          <span className="text-sm">
            No connected models yet. Add a CLI, API, or remote — swarm will
            auto-assign a default from whatever you connect.
          </span>
        </Alert>
      ) : (
        <ul className="space-y-1 text-sm os-scrollable-picker-list" aria-label="Configured LLM profiles">
          {profiles.map((profile) => (
            <li
              key={`${profile.source}:${profile.id}`}
              className="rounded-lg border border-base-300 bg-base-200/60 px-3 py-2"
            >
              <span className="font-mono">{profile.id}</span>
              <span className="ml-2 text-xs text-base-content/60">
                {profile.source}
                {profile.owned_by ? ` · ${profile.owned_by}` : ''}
                {profile.model ? ` · ${profile.model}` : ''}
                {profile.base_url ? ` · ${profile.base_url}` : ''}
              </span>
              <details
                className="mt-2"
                open={
                  focusProviderId ===
                  (profile.source === 'cli'
                    ? `cli:${profile.id}`
                    : profile.source === 'remote'
                      ? `remote:${profile.owned_by || profile.id}`
                      : `llm:${profile.id}`)
                }
              >
                <summary
                  className="cursor-pointer text-sm font-medium"
                  aria-label={`Advanced ${profile.id}`}
                >
                  Advanced
                </summary>
                <ProviderRateLimitFields
                  providerKey={
                    profile.source === 'cli'
                      ? `cli:${profile.id}`
                      : profile.source === 'remote'
                        ? `remote:${profile.owned_by || profile.id}`
                        : `llm:${profile.id}`
                  }
                  autoFocus={
                    focusProviderId ===
                    (profile.source === 'cli'
                      ? `cli:${profile.id}`
                      : profile.source === 'remote'
                        ? `remote:${profile.owned_by || profile.id}`
                        : `llm:${profile.id}`)
                  }
                />
              </details>
            </li>
          ))}
        </ul>
      )}

      <Select
        label="Default"
        name="default-llm-profile"
        value={defaultId}
        onChange={(event) => setDefaultId(event.target.value)}
        size="sm"
        disabled={optionIds.length === 0 || defaultForced}
      >
        {optionIds.length === 0 ? (
          <option value="">No models connected</option>
        ) : null}
        {optionIds.map((id) => (
          <option key={id} value={id}>
            {id}
            {remote?.auto_picks?.default === id && remote.default_is_auto ? ' (auto)' : ''}
          </option>
        ))}
      </Select>
      {remote?.default_is_auto && remote.auto_picks?.default ? (
        <p className="text-xs text-base-content/60">
          Auto-picked Default: <code>{remote.auto_picks.default}</code>. Chat
          uses this until you save another id.
        </p>
      ) : null}
      <EnvOverrideBadge badge={defaultBadge} />

      {addingProfile ? (
        <LlmProfileAddForm
          className={`max-h-[min(70vh,36rem)] space-y-3 overflow-y-auto rounded-box p-4 ${OVERLAY_CHROME_CLASSES}`}
          onCancel={resetAddForm}
          onSaved={async () => {
            resetAddForm()
            hydrated.current = false
            await profilesQuery.refetch()
          }}
        />
      ) : (
        <Button type="button" variant="outline" size="sm" onClick={() => setAddingProfile(true)}>
          Add LLM profile
        </Button>
      )}

      <button
        type="button"
        className="btn btn-outline btn-sm"
        data-testid="override-per-task-button"
        aria-haspopup="dialog"
        aria-expanded={overridePopupOpen}
        onClick={() => setOverridePopupOpen((open) => !open)}
      >
        <span className="label-text">Override per task</span>
        <span
          className={`badge badge-sm ${overrideOn ? 'badge-primary' : 'badge-ghost'}`}
          data-testid="override-per-task-state"
        >
          {overrideOn ? 'On' : 'Off'}
        </span>
        <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
      <p className="text-xs text-base-content/60">
        Off: every job uses Default. On: cheap summary stays on auxiliary,
        design / coding can use delegation.
      </p>

      {overridePopupOpen ? (
        <div
          role="dialog"
          aria-label="Per-task LLM overrides"
          data-testid="override-per-task-popup"
          className={`max-h-[min(70vh,36rem)] space-y-3 overflow-y-auto rounded-box p-4 ${OVERLAY_CHROME_CLASSES}`}
        >
          <div className="flex items-center justify-between gap-2">
            <h5 className="text-sm font-semibold">What can be overridden per task</h5>
            <button
              type="button"
              className="btn btn-ghost btn-xs"
              aria-label="Close overrides popup"
              onClick={() => setOverridePopupOpen(false)}
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={overrideOn}
            className="flex items-center gap-3 text-left"
            data-testid="override-per-task-switch"
            onClick={() => setOverrideOn((on) => !on)}
          >
            <input
              type="checkbox"
              className="toggle toggle-primary pointer-events-none"
              checked={overrideOn}
              readOnly
              tabIndex={-1}
              aria-hidden="true"
            />
            <span className="label-text">Override per task</span>
          </button>
          <p className="text-xs text-base-content/60">
            On: each task class below gets its own profile (auto-filled from
            Default until you change it). Off: every job uses Default. The map
            is kept when you switch off, so re-enabling loses nothing.
          </p>
          <ul className="space-y-2">
            {overrideTaskKinds.map((entry) => {
              const enabled = entry.enabled
              return (
                <li key={entry.id} className="flex items-start justify-between gap-3">
                  <span>
                    <span className="text-sm font-medium">{entry.label}</span>
                    <span className="block text-xs text-base-content/60">{entry.reason}</span>
                  </span>
                  {enabled ? (
                    <span className="badge badge-success badge-sm" data-testid={`override-kind-${entry.id}-on`}>Supported</span>
                  ) : (
                    <span
                      className="tooltip tooltip-left"
                      data-tip={entry.unavailableReason}
                      tabIndex={0}
                    >
                      <span
                        className="badge badge-ghost badge-sm opacity-60"
                        data-testid={`override-kind-${entry.id}-off`}
                      >
                        N/A
                      </span>
                    </span>
                  )}
                </li>
              )
            })
            }
          </ul>
          <p className="text-xs text-base-content/60">
            API only, for now. Other kinds light up here by declaring override
            support — nothing in this popup is a hardcoded kind list.
          </p>
        </div>
      ) : null}

      {overrideOn ? (
        <fieldset className="space-y-3">
          <legend className="text-sm font-medium">Task class map</legend>
          {(['orchestration', 'auxiliary', 'delegation'] as const).map((cls) => (
            <Select
              key={cls}
              label={TASK_CLASS_LABELS[cls]}
              name={`task-llm-${cls}`}
              value={taskMap[cls] || defaultId}
              onChange={(event) =>
                setTaskMap((current) => ({ ...current, [cls]: event.target.value }))
              }
              size="sm"
              disabled={optionIds.length === 0}
            >
              {optionIds.map((id) => (
                <option key={`${cls}-${id}`} value={id}>
                  {id}
                </option>
              ))}
            </Select>
          ))}
        </fieldset>
      ) : null}

      {warnings.length > 0 ? (
        <Alert type="warning" icon={<AlertCircle className="h-5 w-5" />}>
          <ul className="space-y-1 text-sm">
            {warnings.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </Alert>
      ) : null}

      <Button
        type="submit"
        variant="primary"
        size="sm"
        disabled={
          saving ||
          profilesQuery.isPending ||
          profilesQuery.isError ||
          profiles.length === 0 ||
          defaultForced
        }
      >
        {saving ? 'Saving…' : 'Save LLM profiles'}
      </Button>
    </form>
  )
}
