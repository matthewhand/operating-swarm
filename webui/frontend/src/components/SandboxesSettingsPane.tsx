import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiPut } from '../lib/api'

export interface SandboxProviderDescriptor {
  id: string
  label: string
  description: string
  dangerous?: boolean
  requires?: string[]
}

export interface SandboxSettings {
  provider: string
  enable_sandbox_tools: boolean
  timeout_seconds: number
  work_dir: string
  daytona_api_key_env: string
  daytona_api_url: string
  dangerous_confirmed: boolean
  inherit_env?: boolean
  auto_stop_interval?: number
  sync_workspace?: boolean
  providers: SandboxProviderDescriptor[]
  secrets: { daytona_api_key_env: string | null; daytona_api_url: string | null }
}

export interface SandboxProbeResult {
  ok: boolean
  provider: string
  detail: string
  duration_ms?: number
}

const PROVIDER_HELP: Record<string, string> = {
  none: 'Execution tools are not attached to any agent. Safe default.',
  bare_metal: 'Agents execute Python/Bash directly on this host with no isolation.',
  daytona: 'Agents execute inside isolated Daytona microVMs (cloud).',
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message
  return 'Could not load sandbox settings.'
}

export default function SandboxesSettingsPane() {
  const queryClient = useQueryClient()
  const settingsQuery = useQuery({
    queryKey: ['settings-sandbox'],
    queryFn: () => apiGet<SandboxSettings>('/v1/settings/sandbox/'),
    retry: 1,
  })

  const [provider, setProvider] = useState<string>('none')
  const [timeoutSeconds, setTimeoutSeconds] = useState<number>(30)
  const [apiKeyEnv, setApiKeyEnv] = useState<string>('')
  const [apiUrl, setApiUrl] = useState<string>('')
  const [inheritEnv, setInheritEnv] = useState<boolean>(true)
  const [confirmDangerous, setConfirmDangerous] = useState<boolean>(false)
  const [autoStopInterval, setAutoStopInterval] = useState<number>(15)
  const [syncWorkspace, setSyncWorkspace] = useState<boolean>(false)
  const [dirty, setDirty] = useState<boolean>(false)

  // Sync local state from the server payload whenever it arrives.
  useEffect(() => {
    const data = settingsQuery.data
    if (!data) return
    setProvider(data.provider)
    setTimeoutSeconds(data.timeout_seconds ?? 30)
    setApiKeyEnv(data.daytona_api_key_env ?? '')
    setApiUrl(data.daytona_api_url ?? '')
    setInheritEnv(data.inherit_env ?? data.provider === 'bare_metal')
    setConfirmDangerous(Boolean(data.dangerous_confirmed))
    setAutoStopInterval(data.auto_stop_interval ?? 15)
    setSyncWorkspace(Boolean(data.sync_workspace))
    setDirty(false)
  }, [settingsQuery.data])

  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiPut<SandboxSettings>('/v1/settings/sandbox/', body),
    onSuccess: (saved) => {
      queryClient.setQueryData(['settings-sandbox'], saved)
      setProvider(saved.provider)
      setTimeoutSeconds(saved.timeout_seconds ?? 30)
      setApiKeyEnv(saved.daytona_api_key_env ?? '')
      setApiUrl(saved.daytona_api_url ?? '')
      setInheritEnv(saved.inherit_env ?? saved.provider === 'bare_metal')
      setConfirmDangerous(Boolean(saved.dangerous_confirmed))
      setAutoStopInterval(saved.auto_stop_interval ?? 15)
      setSyncWorkspace(Boolean(saved.sync_workspace))
      setDirty(false)
    },
  })

  const probe = useMutation({
    mutationFn: (target: string) =>
      apiPost<SandboxProbeResult>('/v1/settings/sandbox/test', { provider: target }),
  })

  if (settingsQuery.isPending) {
    return (
      <p className="text-sm text-base-content/60" data-testid="settings-sandboxes-pane">
        Loading sandbox settings…
      </p>
    )
  }

  if (settingsQuery.isError || !settingsQuery.data) {
    return (
      <div className="space-y-3" data-testid="settings-sandboxes-pane">
        <p className="text-sm text-error">{errorMessage(settingsQuery.error)}</p>
      </div>
    )
  }

  const providers = settingsQuery.data.providers ?? []
  const selected = providers.find((p) => p.id === provider)
  const saveError = save.error ? errorMessage(save.error) : null

  return (
    <div className="space-y-4" data-testid="settings-sandboxes-pane">
      <p className="text-xs text-base-content/60">
        Sandbox provider for agent code-execution tools. The default (None) attaches no
        execution tools. Secrets are stored as environment-variable <em>names</em> — never
        values.
      </p>

      <div className="grid gap-2" role="radiogroup" aria-label="Sandbox provider">
        {providers.map((p) => {
          const active = p.id === provider
          return (
            <button
              key={p.id}
              type="button"
              role="radio"
              aria-checked={active}
              data-testid={`sandbox-provider-${p.id}`}
              onClick={() => {
                setProvider(p.id)
                if (p.id === 'bare_metal') {
                  setInheritEnv(true)
                }
                setDirty(true)
                probe.reset()
              }}
              className={`rounded-xl border p-3 text-left transition-colors ${
                active
                  ? 'border-primary bg-primary/10'
                  : 'border-base-300 hover:border-base-content/30'
              }`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold">{p.label}</span>
                {p.dangerous ? (
                  <span
                    className="badge badge-error badge-sm"
                    data-testid="sandbox-dangerous-badge"
                  >
                    dangerous
                  </span>
                ) : p.id === 'none' ? (
                  <span className="badge badge-ghost badge-sm">default</span>
                ) : null}
                {(p.requires ?? []).map((req) => (
                  <span key={req} className="badge badge-outline badge-xs">
                    {req}
                  </span>
                ))}
              </div>
              <p className="mt-1 text-xs text-base-content/70">{p.description}</p>
              {active ? (
                <p className="mt-1 text-xs text-base-content/50">{PROVIDER_HELP[p.id]}</p>
              ) : null}
            </button>
          )
        })}
      </div>

      {provider === 'none' ? (
        <p className="text-xs text-base-content/50" data-testid="sandbox-tools-off-note">
          No execution tools are attached. Pick Bare metal host or Daytona to equip
          agents with sandbox_run_bash / sandbox_run_python / file tools.
        </p>
      ) : (
        <p className="text-xs text-base-content/60" data-testid="sandbox-tools-on-note">
          Execution tools attach automatically: sandbox_run_bash, sandbox_run_python,
          sandbox_read_file, sandbox_write_file.
        </p>
      )}

      <label className="block text-sm">
        <span className="text-xs font-semibold uppercase tracking-wide text-base-content/50">
          Timeout (seconds)
        </span>
        <input
          type="number"
          min={1}
          max={600}
          className="input input-bordered mt-1 w-32"
          value={timeoutSeconds}
          data-testid="sandbox-timeout-input"
          onChange={(e) => {
            setTimeoutSeconds(Number(e.target.value) || 30)
            setDirty(true)
          }}
        />
      </label>

      {provider === 'daytona' ? (
        <div className="space-y-2 rounded-xl border border-base-300 p-3" data-testid="daytona-options">
          <label className="block text-sm">
            <span className="text-xs font-semibold uppercase tracking-wide text-base-content/50">
              Daytona API key — env var NAME
            </span>
            <input
              type="text"
              className="input input-bordered mt-1 w-full font-mono"
              placeholder="DAYTONA_API_KEY"
              value={apiKeyEnv}
              data-testid="daytona-key-env-input"
              onChange={(e) => {
                setApiKeyEnv(e.target.value)
                setDirty(true)
              }}
            />
          </label>
          <label className="block text-sm">
            <span className="text-xs font-semibold uppercase tracking-wide text-base-content/50">
              Daytona API URL (optional)
            </span>
            <input
              type="text"
              className="input input-bordered mt-1 w-full font-mono"
              placeholder="https://app.daytona.io/api"
              value={apiUrl}
              data-testid="daytona-url-input"
              onChange={(e) => {
                setApiUrl(e.target.value)
                setDirty(true)
              }}
            />
          </label>
          {settingsQuery.data.secrets?.daytona_api_key_env ? (
            <p className="text-xs text-base-content/50">
              Key env name on file: <code>{settingsQuery.data.secrets.daytona_api_key_env}</code>{' '}
              (value stays in the environment).
            </p>
          ) : null}
          <label className="block text-sm">
            <span className="text-xs font-semibold uppercase tracking-wide text-base-content/50">
              Auto-stop idle microVMs (minutes, 0 = never)
            </span>
            <input
              type="number"
              min={0}
              max={1440}
              className="input input-bordered mt-1 w-32"
              value={autoStopInterval}
              data-testid="daytona-autostop-input"
              onChange={(e) => {
                setAutoStopInterval(Number(e.target.value) || 0)
                setDirty(true)
              }}
            />
          </label>
          <label className="flex items-start gap-2 text-sm" data-testid="daytona-sync-workspace">
            <input
              type="checkbox"
              className="checkbox checkbox-sm mt-0.5"
              checked={syncWorkspace}
              onChange={(e) => {
                setSyncWorkspace(e.target.checked)
                setDirty(true)
              }}
            />
            <span>Upload this project into the sandbox after it is created.</span>
          </label>
        </div>
      ) : null}

      {provider === 'bare_metal' ? (
        <div className="space-y-2 rounded-xl border border-error/40 p-3" data-testid="bare-metal-options">
          <label className="flex items-start gap-2 text-sm" data-testid="sandbox-confirm-dangerous">
            <input
              type="checkbox"
              className="checkbox checkbox-sm checkbox-error mt-0.5"
              checked={confirmDangerous}
              onChange={(e) => {
                setConfirmDangerous(e.target.checked)
                setDirty(true)
              }}
            />
            <span>
              I understand this runs unsandboxed on this host with swarm&apos;s privileges
              (dangerous).
            </span>
          </label>
          <label className="flex items-start gap-2 text-sm" data-testid="sandbox-inherit-env">
            <input
              type="checkbox"
              className="checkbox checkbox-sm mt-0.5"
              checked={inheritEnv}
              onChange={(e) => {
                setInheritEnv(e.target.checked)
                setDirty(true)
              }}
            />
            <span>
              Inherit the full host environment so git, gh, docker, and other CLIs keep
              their credentials.
            </span>
          </label>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn btn-primary btn-sm"
          disabled={
            !dirty ||
            save.isPending ||
            (provider === 'bare_metal' && !confirmDangerous)
          }
          data-testid="sandbox-save"
          onClick={() =>
            save.mutate({
              provider,
              enable_sandbox_tools: provider !== 'none',
              timeout_seconds: timeoutSeconds,
              daytona_api_key_env: apiKeyEnv.trim(),
              daytona_api_url: apiUrl.trim(),
              confirm_dangerous: provider === 'bare_metal' && confirmDangerous,
              inherit_env: inheritEnv,
              auto_stop_interval: autoStopInterval,
              sync_workspace: syncWorkspace,
            })
          }
        >
          {save.isPending ? 'Saving…' : 'Save'}
        </button>
        <button
          type="button"
          className="btn btn-outline btn-sm"
          disabled={probe.isPending}
          data-testid="sandbox-test"
          onClick={() => probe.mutate(provider)}
        >
          {probe.isPending ? 'Testing…' : 'Test provider'}
        </button>
        {dirty ? (
          <span className="text-xs text-base-content/50" data-testid="sandbox-dirty-hint">
            Unsaved changes
          </span>
        ) : null}
      </div>

      {saveError ? (
        <p className="text-sm text-error" data-testid="sandbox-save-error" role="alert">
          {saveError}
        </p>
      ) : null}
      {save.isSuccess && !dirty ? (
        <p className="text-sm text-success" data-testid="sandbox-save-ok">
          Saved.
        </p>
      ) : null}

      {probe.error ? (
        <p className="text-sm text-error" data-testid="sandbox-probe-error" role="alert">
          {errorMessage(probe.error)}
        </p>
      ) : null}
      {probe.data ? (
        <div
          className={`rounded-xl border p-3 text-sm ${
            probe.data.ok ? 'border-success bg-success/10' : 'border-error bg-error/10'
          }`}
          data-testid="sandbox-probe-result"
        >
          <span className="font-semibold">{probe.data.ok ? 'OK' : 'Failed'}</span> —{' '}
          {probe.data.detail}
          {typeof probe.data.duration_ms === 'number' ? (
            <span className="ml-1 text-xs text-base-content/50">
              ({Math.round(probe.data.duration_ms)} ms)
            </span>
          ) : null}
        </div>
      ) : null}

      {selected && provider === 'bare_metal' ? (
        <p className="text-xs text-base-content/50">
          {PROVIDER_HELP.bare_metal}
        </p>
      ) : null}
    </div>
  )
}
