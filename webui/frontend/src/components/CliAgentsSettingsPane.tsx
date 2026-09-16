import { useEffect, useRef, useState, type FormEvent, type Ref } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Plus, Server, Settings } from 'lucide-react'
import { Alert, Badge, Button, Input, useToast } from './DaisyUI'
import { fetchCliAgents, fetchConfigSection, patchConfigSection } from '../lib/api'
import {
  compactCliRows,
  configuredCliNames,
  focusedCliName,
  type CompactCliRow,
  type CompactCliStatus,
} from '../lib/cliAgents'
import {
  DEFAULT_HOP_MODE,
  DEFAULT_HOP_TOKEN_BUDGET,
  loadHopPrefs,
  saveHopPrefs,
  type HopMode,
} from '../lib/sessionHopPrefs'
import ProviderRateLimitFields from './ProviderRateLimitFields'

function statusLabel(status: CompactCliStatus): string {
  return status === 'not-detected' ? 'not detected' : status
}

function statusBadgeType(status: CompactCliStatus): 'success' | 'info' | 'ghost' {
  if (status === 'configured') return 'success'
  if (status === 'detected') return 'info'
  return 'ghost'
}

function CliRowSettings({
  row,
  open,
  onOpen,
  focusProviderId,
  panelRef,
  onAdd,
  onRemove,
  addPending,
  removePending,
}: {
  row: CompactCliRow
  open: boolean
  onOpen: () => void
  focusProviderId?: string | null
  panelRef?: Ref<HTMLDivElement>
  onAdd: (name: string, cmd: string[]) => void
  onRemove: (name: string) => void
  addPending: boolean
  removePending: boolean
}) {
  return (
    <div
      ref={open ? panelRef : undefined}
      className={`dropdown dropdown-end ${open ? 'dropdown-open' : ''}`}
    >
      <Button
        type="button"
        variant="ghost"
        size="xs"
        className="os-cli-settings-btn btn-square"
        aria-label={`Settings for ${row.name}`}
        aria-expanded={open}
        aria-haspopup="dialog"
        onMouseEnter={onOpen}
        onFocus={onOpen}
        onClick={onOpen}
      >
        <Settings className="h-4 w-4" aria-hidden="true" />
      </Button>
      {open ? (
        <div
          role="dialog"
          aria-label={`${row.name} settings`}
          className="dropdown-content z-20 mt-1 w-80 rounded-box border border-base-300 bg-base-100 p-3 shadow"
        >
          <p className="font-mono text-sm">{row.name}</p>
          <p className="break-all font-mono text-xs text-base-content/60">
            {(row.cmd || []).join(' ') || '—'}
          </p>
          <ProviderRateLimitFields
            providerKey={`cli:${row.name}`}
            autoFocus={focusProviderId === `cli:${row.name}`}
          />
          <div className="mt-2 flex flex-wrap gap-2">
            {row.status === 'configured' ? (
              <Button
                type="button"
                variant="ghost"
                size="xs"
                onClick={() => onRemove(row.name)}
                disabled={removePending}
              >
                Remove
              </Button>
            ) : (
              <Button
                type="button"
                variant="outline"
                size="xs"
                onClick={() => onAdd(row.name, row.cmd)}
                disabled={addPending}
              >
                Add
              </Button>
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}

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
  const [showUnavailable, setShowUnavailable] = useState(false)
  const focusName = focusedCliName(focusProviderId)
  const [openCli, setOpenCli] = useState<string | null>(focusName)
  const openRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (focusName) setOpenCli(focusName)
  }, [focusName])

  useEffect(() => {
    if (!openCli) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpenCli(null)
    }
    const onPointer = (event: MouseEvent) => {
      const target = event.target as Node | null
      if (target && openRef.current?.contains(target)) return
      setOpenCli(null)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onPointer)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onPointer)
    }
  }, [openCli])

  const data = (configQuery.data?.data || {}) as Record<string, { cmd?: string[] }>
  const names = Object.keys(data)
  const configuredFromCatalog = configuredCliNames(catalogQuery.data)
  const configured = names.length > 0 ? names : configuredFromCatalog
  const rows = compactCliRows(catalogQuery.data, data, {
    showUnavailable,
    focusName,
  })

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
      setOpenCli(null)
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
      ) : (
        <>
          {configured.length === 0 && !adding ? (
            <Alert type="info" icon={<Server className="h-5 w-5" />}>
              <span className="text-sm">No CLI agents configured yet.</span>
            </Alert>
          ) : null}

          {rows.length > 0 ? (
            <ul className="space-y-2" aria-label="CLI agents">
              {rows.map((row) => (
                <li
                  key={row.name}
                  data-testid={`cli-row-${row.name}`}
                  data-status={row.status}
                  className={`os-cli-agent-row flex items-center justify-between gap-3 rounded-lg border px-3 py-2 ${
                    row.status === 'configured'
                      ? 'border-base-300 bg-base-200/60'
                      : row.status === 'detected'
                        ? 'border-dashed border-base-300'
                        : 'border-base-300/70'
                  }`}
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-mono text-sm">{row.name}</p>
                      <Badge size="xs" type={statusBadgeType(row.status)} outline>
                        {statusLabel(row.status)}
                      </Badge>
                    </div>
                    <p className="truncate text-xs text-base-content/60">
                      {(row.cmd || []).join(' ') || '—'}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    {row.status === 'detected' ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="xs"
                        onClick={() => handleSuggestAdd(row.name, row.cmd)}
                        disabled={addMutation.isPending}
                      >
                        Add
                      </Button>
                    ) : null}
                    {row.status === 'configured' ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="xs"
                        onClick={() => removeMutation.mutate(row.name)}
                        disabled={removeMutation.isPending}
                      >
                        Remove
                      </Button>
                    ) : null}
                    {row.status !== 'not-detected' ? (
                      <CliRowSettings
                        row={row}
                        open={openCli === row.name}
                        onOpen={() => setOpenCli(row.name)}
                        focusProviderId={focusProviderId}
                        panelRef={openRef}
                        onAdd={handleSuggestAdd}
                        onRemove={(cliName) => removeMutation.mutate(cliName)}
                        addPending={addMutation.isPending}
                        removePending={removeMutation.isPending}
                      />
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          ) : null}

          <label className="flex w-fit cursor-pointer items-center gap-2 text-xs text-base-content/60">
            <input
              type="checkbox"
              className="toggle toggle-xs"
              checked={showUnavailable}
              onChange={(event) => setShowUnavailable(event.target.checked)}
            />
            Show unavailable
          </label>
        </>
      )}

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

      <details className="os-cli-hop-prefs collapse collapse-arrow rounded-box border border-base-300">
        <summary className="collapse-title text-sm font-semibold">When switching CLI</summary>
        <div className="collapse-content space-y-2">
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
        </div>
      </details>
    </div>
  )
}
