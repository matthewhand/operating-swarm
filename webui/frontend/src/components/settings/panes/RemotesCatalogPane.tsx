/** #856 slice B — RemotesCatalogPane (moved verbatim from SettingsSheet.tsx). */
import { useEffect, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Plus, Server, X } from 'lucide-react'
import { Alert, Button, Input, Select, useToast } from '../.././DaisyUI'
import EnvOverrideBadge from '../.././EnvOverrideBadge'
import ProviderRateLimitFields from '../.././ProviderRateLimitFields'
import {
  createRemote,
  deleteRemote,
  fetchRemotes,
} from '../../../lib/api'
import { parseRemotes } from '../../../lib/remotesCatalog'
import { providerDependents, providerUsageLabel } from '../../../lib/providerUsage'
import { RemoteSelect } from '../.././RemoteSelect'
import { RemoteOperatePane } from '../.././RemotesSettings'
import {
  configuredRemotes,
  herdrLocationLabel,
  isHerdrKind,
  remoteKindLabel,
  remoteKinds,
} from '../../../lib/remotes'

export function RemotesCatalogPane({
  startAdding = false,
  focusProviderId = null,
}: {
  startAdding?: boolean
  focusProviderId?: string | null
}) {
  const { success, error: toastError } = useToast()
  const queryClient = useQueryClient()
  const [adding, setAdding] = useState(startAdding)
  const [kind, setKind] = useState('')
  const [remoteId, setRemoteId] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKeyEnv, setApiKeyEnv] = useState('')
  const [herdrMode, setHerdrMode] = useState<'local' | 'ssh'>('local')
  const [sshTarget, setSshTarget] = useState('')
  const [sshIdentityEnv, setSshIdentityEnv] = useState('')
  const [sshAgent, setSshAgent] = useState(true)
  const [selectedId, setSelectedId] = useState('')
  // #573: the available kinds live in a picker popup behind `+ Add remote`, not
  // in an always-visible form on the page. The page shows what is configured;
  // the popup is the single place a kind choice is made.
  const [kindPickerOpen, setKindPickerOpen] = useState(false)
  const addingHerdr = isHerdrKind(kind)

  const remotesQuery = useQuery({
    queryKey: ['remotes-list'],
    queryFn: fetchRemotes,
    retry: 1,
  })
  const catalog = remotesQuery.data
  const configured = configuredRemotes(catalog)
  const kinds = remoteKinds(catalog)
  // #642: the Remove control locks while agents depend on the remote. The
  // backend stamps dependent agents onto each row; persisted per-agent
  // bindings (localStorage) count too. Catalog rows must be parsed so those
  // `agents` lists survive into `configured`.
  const catalogEntries = parseRemotes(catalog)
  const remoteUsage = (remoteId: string) => {
    const count = providerDependents.remote(catalogEntries, remoteId)
    return { count, locked: count > 0, tip: providerUsageLabel(count) }
  }

  useEffect(() => {
    if (!selectedId && configured[0]) setSelectedId(configured[0].id)
  }, [selectedId, configured])

  useEffect(() => {
    // #573: the bind path (zero remotes elsewhere) opens the kind picker, not
    // a pre-selected form — the kind choice always happens in the popup.
    if (startAdding) setKindPickerOpen(true)
  }, [startAdding])

  const addMutation = useMutation({
    mutationFn: () =>
      createRemote({
        kind,
        ...(remoteId.trim() ? { id: remoteId.trim() } : {}),
        ...(addingHerdr
          ? {
              herdr_mode: herdrMode,
              ...(herdrMode === 'local' && baseUrl.trim() ? { base_url: baseUrl.trim() } : {}),
              ...(herdrMode === 'ssh'
                ? {
                    ssh_target: sshTarget.trim(),
                    ...(sshIdentityEnv.trim() ? { ssh_identity_env: sshIdentityEnv.trim() } : {}),
                    ssh_agent: sshAgent,
                  }
                : {}),
            }
          : {
              ...(baseUrl.trim() ? { base_url: baseUrl.trim() } : {}),
              ...(apiKeyEnv.trim() ? { api_key_env: apiKeyEnv.trim() } : {}),
            }),
      }),
    onSuccess: (created) => {
      queryClient.setQueryData(['remotes-list'], (prev: Awaited<ReturnType<typeof fetchRemotes>> | undefined) => ({
        object: 'list' as const,
        kinds: remoteKinds(prev),
        configured: [...configuredRemotes(prev).filter((row) => row.id !== created.id), created],
        data: prev?.data ?? [],
      }))
      void queryClient.invalidateQueries({ queryKey: ['remotes-list'] })
      void queryClient.invalidateQueries({ queryKey: ['configured-remotes'] })
      setAdding(false)
      setRemoteId('')
      setBaseUrl('')
      setApiKeyEnv('')
      setHerdrMode('local')
      setSshTarget('')
      setSshIdentityEnv('')
      setSshAgent(true)
      setKind('')
      setSelectedId(created.id)
      success('Remote added', `${remoteKindLabel(created.kind || created.id, kinds)} is now configured.`)
    },
    onError: (err: Error) => {
      toastError('Could not add remote', err.message)
    },
  })

  const removeMutation = useMutation({
    mutationFn: (remoteId: string) => deleteRemote(remoteId),
    onSuccess: (_void, remoteId) => {
      queryClient.setQueryData(['remotes-list'], (prev: Awaited<ReturnType<typeof fetchRemotes>> | undefined) => ({
        object: 'list' as const,
        kinds: remoteKinds(prev),
        configured: configuredRemotes(prev).filter((row) => row.id !== remoteId),
        data: prev?.data ?? [],
      }))
      void queryClient.invalidateQueries({ queryKey: ['remotes-list'] })
      void queryClient.invalidateQueries({ queryKey: ['configured-remotes'] })
      if (selectedId === remoteId) setSelectedId('')
      success('Remote removed', 'Dropped from Settings and remote dropdowns.')
    },
    onError: (err: Error) => {
      toastError('Could not remove remote', err.message)
    },
  })

  const handleAdd = (event: FormEvent) => {
    event.preventDefault()
    if (!kind) return
    if (addingHerdr && herdrMode === 'ssh' && !sshTarget.trim()) return
    addMutation.mutate()
  }

  const selected = configured.find((remote) => remote.id === selectedId)

  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-lg font-semibold">Remotes</h4>
        <p className="mt-1 text-sm text-base-content/70">
          Only remotes you add appear here and in remote dropdowns. Unused kinds
          stay off the list. Herdr is SSH-shaped (local Herdr vs SSH to a Herdr
          host) — not an HTTP remote like OpenMousBot / Hermes / Rakazo.
        </p>
      </div>

      {remotesQuery.isPending ? (
        <p className="text-sm text-base-content/60" data-testid="remotes-loading">
          Loading remotes…
        </p>
      ) : remotesQuery.isError ? (
        <div className="space-y-3" data-testid="remotes-error">
          <Alert type="error" icon={<AlertCircle className="h-5 w-5" />}>
            <span className="text-sm">Failed to load remotes catalog.</span>
          </Alert>
          <button
            type="button"
            className="btn btn-sm btn-outline"
            onClick={() => void remotesQuery.refetch()}
          >
            Retry
          </button>
        </div>
      ) : (
        <>
          {configured.length > 0 ? (
            <RemoteSelect
              remotes={catalog}
              value={selectedId}
              onChange={setSelectedId}
              label="Remote"
            />
          ) : null}

          {configured.length === 0 && !adding ? (
            <Alert type="info" icon={<Server className="h-5 w-5" />}>
              <span className="text-sm">No remotes configured yet.</span>
            </Alert>
          ) : configured.length === 0 ? null : (
            <ul className="space-y-2 os-scrollable-picker-list" aria-label="Configured remotes">
              {configured.map((remote) => {
                const label = remoteKindLabel(remote.kind || remote.id, kinds)
                return (
                  <li
                    key={remote.id}
                    className="flex items-start justify-between gap-3 rounded-lg border border-base-300 bg-base-200/60 px-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="font-medium">{label}</p>
                      <p className="truncate font-mono text-xs text-base-content/60">
                        {isHerdrKind(remote.id) ? herdrLocationLabel(remote) : remote.base_url || 'localhost'}
                      </p>
                      <div className="mt-1">
                        <EnvOverrideBadge badge={remote.provenance?.base_url} />
                      </div>
                      {remote.provenance?.api_key ? (
                        <div className="mt-1">
                          <EnvOverrideBadge badge={remote.provenance.api_key} />
                        </div>
                      ) : null}
                      <ProviderRateLimitFields
                        providerKey={`remote:${remote.id}`}
                        autoFocus={focusProviderId === `remote:${remote.id}`}
                      />
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="xs"
                      data-testid={`remote-remove-${remote.id}`}
                      onClick={() => {
                        const usage = remoteUsage(remote.id)
                        if (!usage.locked) removeMutation.mutate(remote.id)
                      }}
                      disabled={removeMutation.isPending || remoteUsage(remote.id).locked}
                      aria-disabled={remoteUsage(remote.id).locked ? 'true' : undefined}
                      title={remoteUsage(remote.id).locked ? remoteUsage(remote.id).tip : undefined}
                    >
                      Remove
                    </Button>
                  </li>
                )
              })}
            </ul>
          )}

          {/* Keyed by remote id: without it React reuses this pane across a
              Remote switch, so the previous remote's list, adopted target, and
              result panes leak into the next one (#453 follow-up). */}
          {selected ? <RemoteOperatePane key={selected.id} remote={selected} /> : null}

          {adding && kind ? (
            <form
              className="space-y-3 rounded-box border border-base-300 p-3"
              aria-label="Add remote form"
              onSubmit={handleAdd}
            >
              <p className="text-sm text-base-content/70" data-testid="remotes-add-kind">
                Kind: <strong>{remoteKindLabel(kind, kinds)}</strong>
                <button
                  type="button"
                  className="btn btn-ghost btn-xs ml-2"
                  onClick={() => {
                    setKind('')
                    setKindPickerOpen(true)
                  }}
                >
                  Change
                </button>
              </p>
              <Input
                label="Remote ID (optional)"
                name="remote-id"
                size="sm"
                value={remoteId}
                onChange={(event) => setRemoteId(event.target.value)}
                placeholder={kind === 'trueforge' ? 'e.g. trueforge_prod (defaults to kind)' : 'Defaults to kind'}
                autoComplete="off"
                spellCheck={false}
              />
              {addingHerdr ? (
                <>
                  <p className="text-sm text-base-content/70">
                    Remote Herdr is SSH-shaped — not HTTP. Local talks to Herdr
                    on this host (no SSH). Remote SSHs to that Herdr host, then
                    uses Herdr’s CLIs (agy / pi / grok). Identity is an env-var
                    name only — never paste a private key.
                  </p>
                  <Select
                    label="Herdr location"
                    name="herdr-mode"
                    size="sm"
                    value={herdrMode}
                    onChange={(event) => setHerdrMode(event.target.value === 'ssh' ? 'ssh' : 'local')}
                  >
                    <option value="local">Local Herdr (this host, no SSH)</option>
                    <option value="ssh">Remote Herdr (SSH to Herdr host)</option>
                  </Select>
                  {herdrMode === 'local' ? (
                    <Input
                      label="Local URL (optional)"
                      name="remote-url"
                      value={baseUrl}
                      onChange={(event) => setBaseUrl(event.target.value)}
                      placeholder="http://127.0.0.1 — only if you chose localhost"
                      autoComplete="off"
                      spellCheck={false}
                    />
                  ) : (
                    <>
                      <Input
                        label="Remote target"
                        name="herdr-ssh-target"
                        value={sshTarget}
                        onChange={(event) => setSshTarget(event.target.value)}
                        placeholder="user@host:port, ssh://user@host:port, or plain host"
                        autoComplete="off"
                        spellCheck={false}
                      />
                      <details className="rounded-box border border-base-300 px-3 py-2">
                        <summary className="cursor-pointer select-none text-sm text-base-content/70">
                          Advanced SSH options
                        </summary>
                        <div className="mt-2 flex flex-col gap-2">
                          <Input
                            label="SSH identity env (optional)"
                            name="herdr-ssh-identity-env"
                            value={sshIdentityEnv}
                            onChange={(event) => setSshIdentityEnv(event.target.value)}
                            placeholder="HERDR_SSH_IDENTITY"
                            autoComplete="off"
                            spellCheck={false}
                          />
                          <label className="flex items-center gap-2 text-sm">
                            <input
                              type="checkbox"
                              className="checkbox checkbox-sm"
                              name="herdr-ssh-agent"
                              checked={sshAgent}
                              onChange={(event) => setSshAgent(event.target.checked)}
                            />
                            Use SSH agent
                          </label>
                        </div>
                      </details>
                    </>
                  )}
                </>
              ) : (
                <>
                  <Input
                    label="URL"
                    name="remote-url"
                    value={baseUrl}
                    onChange={(event) => setBaseUrl(event.target.value)}
                    placeholder={kind === 'swarm' ? 'http://127.0.0.1:9' : 'http://127.0.0.1:8802'}
                    autoComplete="off"
                    spellCheck={false}
                  />
                  {kind === 'swarm' ? (
                    <p className="text-sm text-base-content/70">
                      Nested open-swarm is another process (own DB). Do not add this
                      instance as its own remote.
                    </p>
                  ) : null}
                  <Input
                    label="API key env (optional)"
                    name="remote-api-key-env"
                    value={apiKeyEnv}
                    onChange={(event) => setApiKeyEnv(event.target.value)}
                    placeholder="OMB_API_KEY"
                    autoComplete="off"
                    spellCheck={false}
                  />
                </>
              )}
              <div className="flex flex-wrap gap-2">
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  disabled={
                    !kind ||
                    addMutation.isPending ||
                    (addingHerdr && herdrMode === 'ssh' && !sshTarget.trim())
                  }
                >
                  Save remote
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setAdding(false)
                  }}
                >
                  Cancel
                </Button>
              </div>
            </form>
          ) : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-haspopup="dialog"
              aria-expanded={kindPickerOpen}
              data-testid="remotes-add-button"
              onClick={() => setKindPickerOpen((open) => !open)}
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add remote
            </Button>
          )}

          {kindPickerOpen ? (
            <div
              role="dialog"
              aria-label="Available remote kinds"
              data-testid="remotes-kind-popup"
              className="space-y-2 rounded-box border border-base-300 p-3"
            >
              <div className="flex items-center justify-between gap-2">
                <h5 className="text-sm font-semibold">Add a remote</h5>
                <button
                  type="button"
                  className="btn btn-ghost btn-xs"
                  aria-label="Close remote kinds popup"
                  onClick={() => setKindPickerOpen(false)}
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
              <ul className="space-y-1">
                {kinds.map((item) => {
                  // #573: a kind already configured stays visible but disabled
                  // with the reason on hover (the #511 read), except trueforge,
                  // which is deliberately multi-instance (#503).
                  const alreadyConfigured = configured.some(
                    (remote) => (remote.kind || remote.id) === item.id,
                  )
                  const available = !alreadyConfigured || item.id === 'trueforge'
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        className={`btn btn-sm w-full justify-between ${available ? '' : 'btn-disabled'}`}
                        disabled={!available}
                        title={
                          available
                            ? `Add a ${item.label} remote`
                            : `${item.label} is already configured — remove it first or pick another kind`
                        }
                        data-testid={`remote-kind-${item.id}`}
                        onClick={() => {
                          setKind(item.id)
                          setAdding(true)
                          setKindPickerOpen(false)
                        }}
                      >
                        <span>{item.label}</span>
                        {alreadyConfigured ? (
                          <span className="badge badge-ghost badge-sm">configured</span>
                        ) : null}
                      </button>
                    </li>
                  )
                })}
              </ul>
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}
