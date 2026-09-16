import { useMemo, useState, type FormEvent } from 'react'
import { filterRemoteSessionRows, sessionsFromOperateResult } from '../lib/remoteSessions'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Plus, Server } from 'lucide-react'
import { Alert, Button, Input, Select, Textarea, useToast } from './DaisyUI'
import {
  addRemote,
  fetchRemoteRoutines,
  OPERATE_LIST_TIMEOUT_MS,
  OPERATE_SEND_TIMEOUT_MS,
  operateRemote,
  probeRemoteHealth,
  type RemoteConnection,
  type RemoteHealthResult,
  type RemoteKind,
  type RemoteOperateResult,
  type RemoteRoutine,
} from '../lib/api'
import { isOpenMousBotKind, OPENMOUSBOT_LABEL, remoteKindLabel } from '../lib/remoteKinds'
import { herdrLocationLabel, isHerdrKind } from '../lib/remotes'

export const REMOTES_QUERY_KEY = ['settings-remotes'] as const

export function configuredRemoteSection(id: string): `remotes-${string}` {
  return `remotes-${id}`
}

export function EmptyRemotesPane({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-lg font-semibold">Remotes</h4>
        <p className="mt-1 text-sm text-base-content/70">
          No remotes configured. Add a kind to health-check it, list its bots,
          and send a message. Unused kinds stay out of this list.
        </p>
      </div>
      <Button type="button" variant="primary" size="sm" onClick={onAdd}>
        <Plus className="h-4 w-4" aria-hidden="true" />
        Add remote
      </Button>
    </div>
  )
}

export function AddRemoteForm({
  kinds,
  onAdded,
}: {
  kinds: RemoteKind[]
  onAdded: (remote: RemoteConnection) => void
}) {
  const { success, error } = useToast()
  const queryClient = useQueryClient()
  const options = kinds.length
    ? kinds
    : [
        { id: 'hermes', label: 'Hermes' },
        { id: 'omb', label: OPENMOUSBOT_LABEL },
        { id: 'rakazo', label: 'Rakazo' },
        { id: 'herdr', label: 'Herdr' },
      ]
  const [kind, setKind] = useState(options[0]?.id ?? 'omb')
  const [remoteId, setRemoteId] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKeyEnv, setApiKeyEnv] = useState('')
  const [herdrMode, setHerdrMode] = useState<'local' | 'ssh'>('local')
  const [sshHost, setSshHost] = useState('')
  const [sshUser, setSshUser] = useState('')
  const [sshPort, setSshPort] = useState('')
  const [sshIdentityEnv, setSshIdentityEnv] = useState('')
  const [sshAgent, setSshAgent] = useState(true)
  const herdr = isHerdrKind(kind)

  const addMutation = useMutation({
    mutationFn: () =>
      addRemote({
        kind,
        ...(remoteId.trim() ? { id: remoteId.trim() } : {}),
        ...(herdr
          ? {
              herdr_mode: herdrMode,
              ...(herdrMode === 'local' && baseUrl.trim() ? { base_url: baseUrl.trim() } : {}),
              ...(herdrMode === 'ssh'
                ? {
                    ssh_host: sshHost.trim(),
                    ssh_user: sshUser.trim(),
                    ...(sshPort.trim() ? { ssh_port: sshPort.trim() } : {}),
                    ...(sshIdentityEnv.trim() ? { ssh_identity_env: sshIdentityEnv.trim() } : {}),
                    ssh_agent: sshAgent,
                  }
                : {}),
            }
          : {
              base_url: baseUrl.trim(),
              api_key_env: apiKeyEnv.trim() || undefined,
            }),
      }),
    onSuccess: (remote) => {
      queryClient.setQueryData(REMOTES_QUERY_KEY, (prev: { object?: string; kinds?: RemoteKind[]; data?: RemoteConnection[] } | undefined) => {
        const kinds = prev?.kinds ?? []
        const data = [...(prev?.data ?? []).filter((row) => row.id !== remote.id), remote]
        return { object: 'list' as const, kinds, data }
      })
      queryClient.invalidateQueries({ queryKey: REMOTES_QUERY_KEY })
      success('Remote added', remoteKindLabel(remote.id, remote.label))
      onAdded(remote)
    },
    onError: (err: Error) => {
      error('Could not add remote', err.message)
    },
  })

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    addMutation.mutate()
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div>
        <h4 className="text-lg font-semibold">Add remote</h4>
        <p className="mt-1 text-sm text-base-content/70">
          {herdr
            ? 'Herdr is SSH-shaped — not an HTTP remote like OpenMousBot, Hermes, or Rakazo. Local talks to Herdr on this host (no SSH). Remote SSHs to that Herdr host, then uses Herdr’s CLIs there.'
            : 'Pick a kind, then enter a base URL and an optional api-key-env name (placeholder only — never paste a token).'}
        </p>
      </div>
      <Select
        label="Kind"
        name="remote-kind"
        value={kind}
        onChange={(event) => setKind(event.target.value)}
        required
      >
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {remoteKindLabel(option.id, option.label)}
          </option>
        ))}
      </Select>
      <Input
        label="Remote ID (optional)"
        name="remote-id"
        value={remoteId}
        onChange={(event) => setRemoteId(event.target.value)}
        placeholder={kind === 'trueforge' ? 'e.g. trueforge_prod (defaults to kind)' : 'Defaults to kind'}
        autoComplete="off"
        spellCheck={false}
      />
      {herdr ? (
        <>
          <Select
            label="Herdr location"
            name="herdr-mode"
            value={herdrMode}
            onChange={(event) => setHerdrMode(event.target.value === 'ssh' ? 'ssh' : 'local')}
          >
            <option value="local">Local Herdr (this host, no SSH)</option>
            <option value="ssh">Remote Herdr (SSH to Herdr host)</option>
          </Select>
          {herdrMode === 'local' ? (
            <Input
              label="Local URL (optional)"
              name="remote-base-url"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder="http://127.0.0.1 — only if you chose localhost"
              autoComplete="off"
              spellCheck={false}
            />
          ) : (
            <>
              <Input
                label="SSH host"
                name="herdr-ssh-host"
                value={sshHost}
                onChange={(event) => setSshHost(event.target.value)}
                placeholder="herdr.example.test"
                autoComplete="off"
                spellCheck={false}
                required
              />
              <Input
                label="SSH user"
                name="herdr-ssh-user"
                value={sshUser}
                onChange={(event) => setSshUser(event.target.value)}
                placeholder="herdr"
                autoComplete="off"
                spellCheck={false}
                required
              />
              <Input
                label="SSH port (optional)"
                name="herdr-ssh-port"
                value={sshPort}
                onChange={(event) => setSshPort(event.target.value)}
                placeholder="22"
                autoComplete="off"
                spellCheck={false}
              />
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
            </>
          )}
        </>
      ) : (
        <>
          <Input
            label="Base URL"
            name="remote-base-url"
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
            placeholder="http://127.0.0.1:9"
            autoComplete="off"
            spellCheck={false}
            required
          />
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
      <Button type="submit" variant="primary" size="sm" loading={addMutation.isPending}>
        Add remote
      </Button>
    </form>
  )
}

export function botsFromOperate(result: RemoteOperateResult | undefined): Array<{ id: string; name?: string }> {
  if (!result?.data) return []
  const sessions = sessionsFromOperateResult(result)
  if (sessions.length > 0) {
    return sessions.map((row) => ({ id: row.id, name: row.title }))
  }
  const raw = result.data
  let list: unknown = raw
  if (raw && typeof raw === 'object') {
    if ('bots' in raw) {
      list = (raw as { bots: unknown }).bots
    } else if ('members' in raw) {
      list = (raw as { members: unknown }).members
    } else if ('agents' in raw) {
      list = (raw as { agents: unknown }).agents
    } else if ('sessions' in raw) {
      list = (raw as { sessions: unknown }).sessions
    } else if ('data' in raw) {
      const d = (raw as { data: unknown }).data
      if (Array.isArray(d)) {
        list = d
      } else if (d && typeof d === 'object' && 'bots' in d) {
        list = (d as { bots: unknown }).bots
      } else if (d && typeof d === 'object' && 'sessions' in d) {
        list = (d as { sessions: unknown }).sessions
      }
    }
  }
  if (!Array.isArray(list)) return []
  return list
    .map((item) => {
      if (typeof item === 'string') return { id: item }
      if (item && typeof item === 'object') {
        const rec = item as { id?: unknown; name?: unknown; title?: unknown }
        const label =
          rec.name != null ? String(rec.name) : rec.title != null ? String(rec.title) : undefined
        const id = rec.id != null ? String(rec.id) : label || ''
        if (!id) return null
        return { id, name: label }
      }
      return null
    })
    .filter((item): item is { id: string; name?: string } => Boolean(item?.id))
}

export function humanizeCron(cron: string): string {
  const parts = cron.trim().split(/\s+/)
  if (parts.length !== 5) return cron

  const [min, hour, dom, mon, dow] = parts

  if (cron === '* * * * *') return 'Every minute'
  if (min.startsWith('*/') && hour === '*' && dom === '*' && mon === '*' && dow === '*') {
    return `Every ${min.slice(2)} minutes`
  }
  if (min === '0' && hour === '*' && dom === '*' && mon === '*' && dow === '*') {
    return 'Every hour'
  }
  if (min === '0' && hour.startsWith('*/') && dom === '*' && mon === '*' && dow === '*') {
    return `Every ${hour.slice(2)} hours`
  }
  if (dom === '*' && mon === '*') {
    const pad = (v: string) => v.padStart(2, '0')
    const timeStr = `${pad(hour)}:${pad(min)}`
    if (dow === '*') return `Daily at ${timeStr}`
    if (dow === '1-5') return `Weekdays at ${timeStr}`
    if (dow === '0,6' || dow === '6,0' || dow === '6-0' || dow === '0-1') return `Weekends at ${timeStr}`
    const dayNames: Record<string, string> = {
      '0': 'Sunday',
      '1': 'Monday',
      '2': 'Tuesday',
      '3': 'Wednesday',
      '4': 'Thursday',
      '5': 'Friday',
      '6': 'Saturday',
      '7': 'Sunday',
    }
    if (dayNames[dow]) return `Every ${dayNames[dow]} at ${timeStr}`
  }

  return cron
}

export function RemoteOperatePane({ remote }: { remote: RemoteConnection }) {
  const { error } = useToast()
  const label = remoteKindLabel(remote.id, remote.label || remote.title)
  const isOmb = isOpenMousBotKind(remote.id)
  const isHerdr = isHerdrKind(remote.id)
  const hasRoutines = Boolean(remote.capabilities?.routines)
  const [health, setHealth] = useState<RemoteHealthResult | null>(null)
  const [listed, setListed] = useState<RemoteOperateResult | null>(null)
  const [sent, setSent] = useState<RemoteOperateResult | null>(null)
  const [interrogated, setInterrogated] = useState<RemoteOperateResult | null>(null)
  const [botId, setBotId] = useState('')
  const [prompt, setPrompt] = useState('')
  const [sessionQuery, setSessionQuery] = useState('')

  const routinesQuery = useQuery({
    queryKey: ['remote-routines', remote.id],
    queryFn: () => fetchRemoteRoutines(remote.id),
    enabled: hasRoutines && health?.state !== 'DOWN',
    staleTime: 10_000,
  })

  const healthMutation = useMutation({
    mutationFn: () => probeRemoteHealth(remote.id),
    onSuccess: (result) => setHealth(result),
    onError: (err: Error) => {
      setHealth({
        remote: remote.id,
        ok: false,
        state: 'DOWN',
        detail: err.message || 'health probe failed',
      })
    },
  })

  const listMutation = useMutation({
    mutationFn: () => operateRemote(remote.id, { op: 'list' }, { timeoutMs: OPERATE_LIST_TIMEOUT_MS }),
    onSuccess: (result) => {
      setListed(result)
      const bots = botsFromOperate(result)
      if (!botId && bots[0]?.id) setBotId(bots[0].id)
    },
    onError: (err: Error) => {
      setListed({
        remote: remote.id,
        op: 'list',
        ok: false,
        detail: err.message || 'list failed',
      })
    },
  })

  const interrogateMutation = useMutation({
    mutationFn: () =>
      operateRemote(remote.id, { op: 'interrogate', target: botId.trim() }, { timeoutMs: 12000 }),
    onSuccess: (result) => setInterrogated(result),
    onError: (err: Error) => {
      setInterrogated({
        remote: remote.id,
        op: 'interrogate',
        ok: false,
        detail: err.message || 'interrogate failed',
      })
    },
  })

  const sendMutation = useMutation({
    mutationFn: () =>
      operateRemote(
        remote.id,
        {
          op: 'send',
          prompt: prompt.trim(),
          target: botId.trim(),
          session_id: botId.trim() || undefined,
        },
        { timeoutMs: OPERATE_SEND_TIMEOUT_MS },
      ),
    onSuccess: (result) => setSent(result),
    onError: (err: Error) => {
      error('Send failed', err.message)
      setSent({
        remote: remote.id,
        op: 'send',
        ok: false,
        detail: err.message || 'send failed',
      })
    },
  })

  const bots = useMemo(() => botsFromOperate(listed ?? undefined), [listed])
  const visibleBots = useMemo(
    () =>
      filterRemoteSessionRows(
        bots.map((bot) => ({ id: bot.id, title: bot.name || bot.id })),
        sessionQuery,
      ).map((row) => ({ id: row.id, name: row.title !== row.id ? row.title : undefined })),
    [bots, sessionQuery],
  )
  const isSessionsRemote = Boolean(remote.capabilities?.sessions) || ['anythingllm', 'letta', 'openwebui'].includes(remote.id)
  const healthTone =
    health?.state === 'UP' ? 'success' : health?.state === 'DOWN' ? 'warning' : health ? 'info' : undefined

  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-lg font-semibold">{label}</h4>
        <p className="mt-1 text-sm text-base-content/70">
          {isHerdr
            ? herdrLocationLabel(remote)
            : `${remote.base_url || 'No base URL'}${remote.api_key_env ? ` · env ${remote.api_key_env}` : ''}`}
        </p>
        {isHerdr ? (
          <p className="mt-1 text-sm text-base-content/70">
            Remote Herdr is SSH-shaped — not an HTTP remote like OpenMousBot / Hermes / Rakazo.
            Health, list, send, and interrogate go to Herdr on that host (then its CLIs).
          </p>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          loading={healthMutation.isPending}
          onClick={() => healthMutation.mutate()}
        >
          Health
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          loading={listMutation.isPending}
          onClick={() => listMutation.mutate()}
        >
          {isOmb ? 'List bots' : isHerdr ? 'List CLIs' : 'List'}
        </Button>
        {isHerdr ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            loading={interrogateMutation.isPending}
            disabled={!botId.trim()}
            onClick={() => interrogateMutation.mutate()}
          >
            Interrogate CLI
          </Button>
        ) : null}
      </div>

      {health && (
        <Alert
          type={healthTone === 'success' ? 'success' : healthTone === 'warning' ? 'warning' : 'info'}
          icon={<Server className="h-5 w-5" />}
        >
          <div className="space-y-1 text-sm">
            <p>
              <span className="font-medium">{health.state}</span>
              {health.ok ? '' : ' — report, not a crash'}
            </p>
            <p className="text-base-content/70">{health.detail}</p>
          </div>
        </Alert>
      )}

      {listed && (
        <div className="space-y-2">
          <p className="text-sm font-medium">
            {isOmb ? 'Bots' : isHerdr ? 'CLIs / panes' : isSessionsRemote ? 'Sessions' : 'List'}
          </p>
          {listed.ok && bots.length > 5 ? (
            <Input
              label="Search sessions"
              name="remote-session-search"
              value={sessionQuery}
              onChange={(event) => setSessionQuery(event.target.value)}
              placeholder="Filter by name or id"
              autoComplete="off"
              spellCheck={false}
            />
          ) : null}
          {listed.ok && visibleBots.length > 0 ? (
            <ul className="space-y-1 text-sm os-scrollable-picker-list pr-1">
              {visibleBots.map((bot) => (
                <li key={bot.id}>
                  <button
                    type="button"
                    className={`w-full rounded-lg border px-3 py-2 font-mono text-left ${
                      botId === bot.id
                        ? 'border-primary bg-primary/10'
                        : 'border-base-300 bg-base-200/60'
                    }`}
                    onClick={() => setBotId(bot.id)}
                  >
                    {bot.id}
                    {bot.name ? ` · ${bot.name}` : ''}
                  </button>
                </li>
              ))}
            </ul>
          ) : listed.ok && bots.length > 0 && visibleBots.length === 0 ? (
            <Alert type="info" icon={<AlertCircle className="h-5 w-5" />}>
              <span className="text-sm">No sessions match “{sessionQuery}”.</span>
            </Alert>
          ) : (
            <Alert type={listed.ok ? 'info' : 'warning'} icon={<AlertCircle className="h-5 w-5" />}>
              <span className="text-sm">{listed.detail}</span>
            </Alert>
          )}
        </div>
      )}

      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault()
          sendMutation.mutate()
        }}
      >
        <Input
          label={isOmb ? 'Bot id' : isHerdr ? 'CLI / pane' : 'Target'}
          name="remote-bot-id"
          value={botId}
          onChange={(event) => setBotId(event.target.value)}
          placeholder={isOmb ? 'bot id' : isHerdr ? 'w3:p1 or grok' : 'optional target'}
          autoComplete="off"
          spellCheck={false}
        />
        <Textarea
          label="Message"
          name="remote-send-prompt"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="Message to send"
          rows={3}
          required
        />
        <Button type="submit" variant="primary" size="sm" loading={sendMutation.isPending}>
          Send
        </Button>
      </form>

      {interrogated && (
        <Alert type={interrogated.ok ? 'success' : 'warning'} icon={<AlertCircle className="h-5 w-5" />}>
          <span className="text-sm">{interrogated.detail}</span>
        </Alert>
      )}
      {sent && (
        <Alert type={sent.ok ? 'success' : 'warning'} icon={<AlertCircle className="h-5 w-5" />}>
          <span className="text-sm">{sent.detail}</span>
        </Alert>
      )}

      {hasRoutines && health?.state !== 'DOWN' && (
        <div className="space-y-3 border-t border-base-300 pt-4" data-testid="remote-routines-section">
          <div className="flex items-center justify-between">
            <h5 className="text-sm font-semibold text-base-content">
              Routines (TrueForge schedules)
            </h5>
            <Button
              type="button"
              variant="ghost"
              size="xs"
              loading={routinesQuery.isFetching}
              onClick={() => void routinesQuery.refetch()}
            >
              Refresh
            </Button>
          </div>

          {routinesQuery.isPending ? (
            <p className="text-sm text-base-content/60" data-testid="remote-routines-loading">
              Loading routines…
            </p>
          ) : routinesQuery.isError ? (
            <Alert type="warning" icon={<AlertCircle className="h-5 w-5" />}>
              <span className="text-sm">
                {routinesQuery.error?.message || 'Failed to load routines'}
              </span>
            </Alert>
          ) : ((routinesQuery.data?.data?.routines ?? []) as RemoteRoutine[]).length === 0 ? (
            <p className="text-sm text-base-content/60" data-testid="remote-routines-empty">
              No routines configured on this remote.
            </p>
          ) : (
            <ul className="space-y-2 os-scrollable-picker-list" data-testid="remote-routines-list">
              {((routinesQuery.data?.data?.routines ?? []) as RemoteRoutine[]).map((routine) => {
                const isActive = (routine.status || 'active').toLowerCase() === 'active'
                const lastRun = routine.last_run
                const lastRunStatus = (lastRun?.status || '').toLowerCase()
                const scheduleHuman = humanizeCron(routine.cron || '')
                return (
                  <li
                    key={routine.id || routine.name}
                    className="rounded-lg border border-base-300 bg-base-200/50 p-3 space-y-1.5 text-sm"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-base-content">{routine.name}</span>
                      <span
                        className={`badge badge-sm ${
                          isActive ? 'badge-success' : 'badge-ghost text-base-content/70'
                        }`}
                      >
                        {routine.status || 'active'}
                      </span>
                    </div>

                    <div className="text-xs text-base-content/80 space-y-0.5">
                      {routine.agent && (
                        <p>
                          <span className="font-medium">Agent:</span> {routine.agent}
                        </p>
                      )}
                      {routine.cron && (
                        <p>
                          <span className="font-medium">Schedule:</span> {routine.cron}
                          {scheduleHuman && scheduleHuman !== routine.cron
                            ? ` (${scheduleHuman})`
                            : ''}
                          {routine.timezone ? ` · ${routine.timezone}` : ''}
                        </p>
                      )}
                      {routine.task && (
                        <p className="truncate">
                          <span className="font-medium">Task:</span> {routine.task}
                        </p>
                      )}
                    </div>

                    <div className="border-t border-base-300/50 pt-1.5 text-xs text-base-content/70 flex items-center justify-between">
                      <span>Last run:</span>
                      {lastRun ? (
                        <span className="flex items-center gap-1.5">
                          <span
                            className={`badge badge-xs ${
                              lastRunStatus === 'triggered'
                                ? 'badge-success'
                                : lastRunStatus === 'failed'
                                ? 'badge-error'
                                : 'badge-ghost'
                            }`}
                          >
                            {lastRun.status || 'unknown'}
                          </span>
                          <span>{lastRun.scheduled_for || '—'}</span>
                        </span>
                      ) : (
                        <span>No runs recorded</span>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
