import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Plus, Server } from 'lucide-react'
import { Alert, Button, Input, useToast } from './DaisyUI'
import { fetchCliAgents, fetchConfigSection, patchConfigSection } from '../lib/api'
import { configuredCliNames, suggestedCliEntries } from '../lib/cliAgents'
import {
  DEFAULT_HOP_MODE,
  DEFAULT_HOP_TOKEN_BUDGET,
  loadHopPrefs,
  saveHopPrefs,
  type HopMode,
} from '../lib/sessionHopPrefs'
import ProviderRateLimitFields from './ProviderRateLimitFields'

export default function CliAgentsSettingsPane({
  focusProviderId = null,
}: {
  focusProviderId?: string | null
} = {}) {
  const { success, error: toastError } = useToast()
  const queryClient = useQueryClient()
  const configQuery = useQuery({
    queryKey: ['settings-cli-agents'],
    queryFn: () => fetchConfigSection('cli_agents'),
    retry: 1,
  })
  const catalogQuery = useQuery({
    queryKey: ['cli-agents'],
    queryFn: fetchCliAgents,
    retry: 1,
  })
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [cmdText, setCmdText] = useState('')
  const [hopPrefs, setHopPrefs] = useState(() => loadHopPrefs())

  const data = (configQuery.data?.data || {}) as Record<string, { cmd?: string[] }>
  const names = Object.keys(data)
  const configuredFromCatalog = configuredCliNames(catalogQuery.data)
  const configured = names.length > 0 ? names : configuredFromCatalog
  const suggestions = suggestedCliEntries(catalogQuery.data)

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['settings-cli-agents'] })
    void queryClient.invalidateQueries({ queryKey: ['cli-agents'] })
  }

  const addMutation = useMutation({
    mutationFn: (entry: { name: string; cmd: string[] }) =>
      patchConfigSection('cli_agents', { upsert: { [entry.name]: { cmd: entry.cmd } } }),
    onSuccess: (_void, entry) => {
      invalidate()
      setAdding(false)
      setName('')
      setCmdText('')
      success('CLI agent saved', `${entry.name} is now configured.`)
    },
    onError: (err: Error) => {
      toastError('Could not save CLI agent', err.message)
    },
  })

  const removeMutation = useMutation({
    mutationFn: (cliName: string) => patchConfigSection('cli_agents', { delete: [cliName] }),
    onSuccess: () => {
      invalidate()
      success('CLI agent removed', 'Dropped from swarm_config.json. It may still appear as a suggestion if the binary is on PATH.')
    },
    onError: (err: Error) => {
      toastError('Could not remove CLI agent', err.message)
    },
  })

  const handleAdd = (event: FormEvent) => {
    event.preventDefault()
    if (!name.trim() || !cmdText.trim()) return
    const cmd = cmdText
      .split(',')
      .map((part) => part.trim())
      .filter(Boolean)
    addMutation.mutate({ name: name.trim(), cmd })
  }

  const handleSuggestAdd = (cliName: string, cmd: string[]) => {
    addMutation.mutate({ name: cliName, cmd: cmd.length ? cmd : [cliName] })
  }

  const loading = configQuery.isPending || catalogQuery.isPending
  const failed = configQuery.isError && catalogQuery.isError

  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-lg font-semibold">CLI agents</h4>
        <p className="mt-1 text-sm text-base-content/70">
          Only CLIs you add appear here and in the chat CLI dropdown. Startup
          discovers installed binaries (grok, agy, claude, gemini, codex,
          opencode, pi) without checking auth. Each CLI keeps its own login —
          Operating Swarm never stores those secrets.
        </p>
      </div>

      {loading ? (
        <p className="text-sm text-base-content/60">Loading CLI agents…</p>
      ) : failed ? (
        <Alert type="warning" icon={<AlertCircle className="h-5 w-5" />}>
          <span className="text-sm">Could not load cli_agents from config.</span>
        </Alert>
      ) : configured.length === 0 && !adding ? (
        <Alert type="info" icon={<Server className="h-5 w-5" />}>
          <span className="text-sm">No CLI agents configured yet.</span>
        </Alert>
      ) : configured.length === 0 ? null : (
        <ul className="space-y-2" aria-label="Configured CLI agents">
          {configured.map((cliName) => (
            <li
              key={cliName}
              className="flex items-start justify-between gap-3 rounded-lg border border-base-300 bg-base-200/60 px-3 py-2"
            >
              <div className="min-w-0">
                <p className="font-mono text-sm">{cliName}</p>
                <p className="truncate text-xs text-base-content/60">
                  {(data[cliName]?.cmd || []).join(' ') || '—'}
                </p>
                <ProviderRateLimitFields
                  providerKey={`cli:${cliName}`}
                  autoFocus={focusProviderId === `cli:${cliName}`}
                />
              </div>
              <Button
                type="button"
                variant="ghost"
                size="xs"
                onClick={() => removeMutation.mutate(cliName)}
                disabled={removeMutation.isPending}
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
      )}

      {suggestions.length > 0 ? (
        <div className="space-y-2">
          <h5 className="text-sm font-semibold">Suggested</h5>
          <p className="text-xs text-base-content/60">
            Found on this host (no auth check). One-click add persists like remotes.
          </p>
          <ul className="space-y-2" aria-label="Suggested CLI agents">
            {suggestions.map((row) => (
              <li
                key={row.name}
                className="flex items-start justify-between gap-3 rounded-lg border border-dashed border-base-300 px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="font-mono text-sm">{row.name}</p>
                  <p className="truncate text-xs text-base-content/60">{row.cmd.join(' ')}</p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="xs"
                  onClick={() => handleSuggestAdd(row.name, row.cmd)}
                  disabled={addMutation.isPending}
                >
                  Add
                </Button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {adding ? (
        <form className="space-y-3 rounded-box border border-base-300 p-3" onSubmit={handleAdd}>
          <Input
            label="Name"
            name="cli-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="grok"
            autoComplete="off"
            spellCheck={false}
          />
          <Input
            label="Command (comma-separated)"
            name="cli-cmd"
            value={cmdText}
            onChange={(event) => setCmdText(event.target.value)}
            placeholder="grok"
            autoComplete="off"
            spellCheck={false}
          />
          <div className="flex flex-wrap gap-2">
            <Button
              type="submit"
              variant="primary"
              size="sm"
              disabled={!name.trim() || !cmdText.trim() || addMutation.isPending}
            >
              Save CLI agent
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setAdding(false)}>
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <Button type="button" variant="outline" size="sm" onClick={() => setAdding(true)}>
          <Plus className="h-4 w-4" aria-hidden="true" />
          Add CLI agent
        </Button>
      )}

      <fieldset className="space-y-2 rounded-box border border-base-300 p-3">
        <legend className="px-1 text-sm font-semibold">When switching CLI</legend>
        <p className="text-sm text-base-content/70">
          Quota hop starts a <strong>new</strong> session on the target CLI and seeds it with
          prior swarm context. Switching back is also a new session. Secrets and tool noise are
          omitted. Manual switch only — no automatic failover.
        </p>
        <div className="flex flex-wrap gap-3" role="radiogroup" aria-label="Hop context mode">
          {(['summary', 'full'] as HopMode[]).map((mode) => (
            <label key={mode} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="session-hop-mode"
                className="radio radio-sm"
                checked={hopPrefs.mode === mode}
                onChange={() => setHopPrefs(saveHopPrefs({ mode }))}
              />
              {mode === DEFAULT_HOP_MODE ? 'Summary (default)' : 'Full'}
            </label>
          ))}
        </div>
        <label className="form-control w-full max-w-xs">
          <span className="label-text text-sm">Token budget for injected context</span>
          <Input
            name="hop-token-budget"
            type="number"
            min={64}
            max={128000}
            value={String(hopPrefs.tokenBudget || DEFAULT_HOP_TOKEN_BUDGET)}
            onChange={(event) =>
              setHopPrefs(saveHopPrefs({ tokenBudget: Number(event.target.value) }))
            }
          />
        </label>
      </fieldset>
    </div>
  )
}
