/**
 * #1397 — per-agent plugin pack / import / status. Ids only; never tokens.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertCircle, Copy, Download, PackagePlus, RefreshCw } from 'lucide-react'
import { Alert, Button, Textarea, useOptionalToast } from './DaisyUI'
import {
  ApiError,
  fetchAgentPluginPack,
  fetchAgentPlugins,
  importAgentPluginPack,
  installMarketplaceItem,
} from '../lib/api'
import {
  MEMORY_ONLY_NOTE,
  PluginPackClientError,
  checklistState,
  displayTextIsSafe,
  parsePackInput,
  publicPackJson,
  publicStatusFromPayload,
  selectedPack,
  validatePack,
} from '../lib/agentPluginPack'
import { openSettingsSheet } from './settings/kernel'
import type { AgentPluginIdRow, AgentPluginStatusRow, AgentPluginsStatus } from '../lib/api'

export interface AgentPluginPackPaneProps {
  agentId: string
  compact?: boolean
}

function statusLabel(status: AgentPluginStatusRow['status']): string {
  return status === 'enabled' ? 'Enabled' : 'Missing'
}

function friendlyError(err: unknown): string {
  if (err instanceof PluginPackClientError) return err.message
  if (err instanceof ApiError) {
    const text = err.message.trim()
    if (text && displayTextIsSafe(text)) return text
    return 'Plugin pack request failed.'
  }
  if (err instanceof Error && err.message && displayTextIsSafe(err.message)) {
    return err.message
  }
  return 'Plugin pack request failed.'
}

function countByStatus(rows: AgentPluginStatusRow[]): { enabled: number; missing: number } {
  return {
    enabled: rows.filter((row) => row.status === 'enabled').length,
    missing: rows.filter((row) => row.status === 'missing').length,
  }
}

export default function AgentPluginPackPane({ agentId, compact = false }: AgentPluginPackPaneProps) {
  const toast = useOptionalToast()
  const [status, setStatus] = useState<AgentPluginsStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState('')
  const [draft, setDraft] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const requestRef = useRef(0)

  const load = useCallback(async () => {
    const agent = agentId.trim()
    const request = ++requestRef.current
    if (!agent) {
      setStatus(null)
      setError('')
      setLoading(false)
      return
    }
    setLoading(true)
    setError('')
    try {
      const payload = publicStatusFromPayload(await fetchAgentPlugins(agent))
      if (request !== requestRef.current) return
      setStatus(payload)
      setSelected(packableIds(payload))
    } catch (err) {
      if (request !== requestRef.current) return
      setStatus(null)
      setSelected([])
      setError(friendlyError(err))
    } finally {
      if (request === requestRef.current) setLoading(false)
    }
  }, [agentId])

  useEffect(() => {
    void load()
    return () => {
      requestRef.current += 1
    }
  }, [load])

  const copyPack = async () => {
    const agent = agentId.trim()
    if (!agent) return
    try {
      const full = status?.pack
        ? validatePack(status.pack)
        : validatePack(await fetchAgentPluginPack(agent))
      const pack = selected.length ? selectedPack(full.plugins, selected) : full
      const text = publicPackJson(pack)
      if (!displayTextIsSafe(text)) {
        throw new PluginPackClientError('Pack contained a credential and was refused.', 'plugin_pack_secrets')
      }
      if (typeof navigator === 'undefined' || !navigator.clipboard?.writeText) {
        throw new PluginPackClientError(
          'Clipboard is not available in this browser.',
          'plugin_pack_clipboard',
        )
      }
      await navigator.clipboard.writeText(text)
      toast?.success('Pack copied', 'Plugin ids only — no tokens.')
    } catch (err) {
      const message = friendlyError(err)
      setError(message)
      toast?.error('Could not copy pack', message)
    }
  }

  const importDraft = async () => {
    const agent = agentId.trim()
    if (!agent) return
    setImporting(true)
    setError('')
    try {
      const pack = parsePackInput(draft)
      const payload = publicStatusFromPayload(await importAgentPluginPack(agent, pack))
      setStatus(payload)
      setSelected(packableIds(payload))
      const counts = countByStatus(payload?.plugins ?? [])
      const missing = counts.missing
      const enabled = counts.enabled
      toast?.success(
        'Pack imported',
        missing
          ? `${enabled} enabled on this host, ${missing} missing.`
          : `${enabled} plugin${enabled === 1 ? '' : 's'} enabled on this host.`,
      )
    } catch (err) {
      const message = friendlyError(err)
      setError(message)
      if (err instanceof PluginPackClientError && err.code === 'plugin_pack_secrets') {
        setDraft('')
      }
      toast?.error('Could not import pack', message)
    } finally {
      setImporting(false)
    }
  }

  if (!agentId.trim()) {
    return (
      <div className="os-plugin-pack" data-testid="os-plugin-pack-pane">
        <p className="text-sm text-base-content/60">
          Select an agent to pack, import, or inspect plugin-id status.
        </p>
      </div>
    )
  }

  const rows = status?.plugins ?? []
  const counts = countByStatus(rows)
  const packable = packableRows(status)
  const memoryNamed = status?.memory_named ?? []

  const toggleSelected = (pluginId: string) => {
    setSelected((current) =>
      current.includes(pluginId) ? current.filter((id) => id !== pluginId) : [...current, pluginId],
    )
  }

  const connectPlugin = async (pluginId: string) => {
    setError('')
    try {
      await installMarketplaceItem('plugins', pluginId)
    } catch (err) {
      setError(friendlyError(err))
    }
    openSettingsSheet({ section: 'plugins' })
  }

  return (
    <div className="os-plugin-pack space-y-3" data-testid="os-plugin-pack-pane" data-agent={agentId}>
      <div>
        <h4 className={compact ? 'text-sm font-semibold' : 'text-lg font-semibold'}>Plugin pack</h4>
        <p className="mt-1 text-sm text-base-content/70">
          Pack and import <strong>plugin ids</strong> for this agent. Status is
          enabled or missing on this host. Tokens, URLs, commands, and env
          values are never shown.
        </p>
      </div>

      {error ? (
        <Alert type="warning" icon={<AlertCircle className="h-5 w-5" />}>
          <span className="text-sm" data-testid="os-plugin-pack-error">
            {error}
          </span>
        </Alert>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => void load()}
          disabled={loading}
          data-testid="os-plugin-pack-refresh"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          Refresh status
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => void copyPack()}
          disabled={loading}
          data-testid="os-plugin-pack-copy"
        >
          <Copy className="h-3.5 w-3.5" aria-hidden="true" />
          Copy pack
        </Button>
      </div>

      {packable.length ? (
        <fieldset className="space-y-1" data-testid="os-plugin-pack-select">
          <legend className="text-sm font-medium">Packable plugins</legend>
          {packable.map((row) => (
            <label key={row.pluginId} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={selected.includes(row.pluginId)}
                onChange={() => toggleSelected(row.pluginId)}
                aria-label={`Pack ${row.name || row.pluginId}`}
              />
              <span>{row.name || row.pluginId}</span>
            </label>
          ))}
        </fieldset>
      ) : null}

      {memoryNamed.length ? (
        <ul className="space-y-1 text-sm" aria-label="Non-packable plugins" data-testid="os-plugin-memory-only">
          {memoryNamed.map((row) => (
            <li key={row.name} data-memory-only="true">
              {row.name} {MEMORY_ONLY_NOTE}
            </li>
          ))}
        </ul>
      ) : null}

      {loading && !status ? (
        <p className="text-sm text-base-content/60" role="status">
          Loading plugin status…
        </p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-base-content/60" data-testid="os-plugin-pack-empty">
          No plugin ids packed for this agent yet. Import a pack below.
        </p>
      ) : (
        <ul
          className="os-plugin-pack__list space-y-2"
          aria-label="Plugin pack status"
          data-testid="os-plugin-pack-status"
        >
          {rows.map((row) => (
            <li
              key={row.pluginId}
              className="os-plugin-pack__row rounded-lg border border-base-300 p-3"
              data-plugin-id={row.pluginId}
              data-status={row.status}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium">{row.name || row.pluginId}</p>
                  <p className="truncate font-mono text-xs text-base-content/55">{row.pluginId}</p>
                  {row.description ? (
                    <p className="mt-0.5 text-xs text-base-content/60">{row.description}</p>
                  ) : null}
                  {row.required_env?.length ? (
                    <p className="mt-1 text-xs text-base-content/50">
                      Env names: {row.required_env.join(', ')}
                    </p>
                  ) : null}
                </div>
                <span
                  className={
                    row.status === 'enabled'
                      ? 'badge badge-success badge-sm'
                      : 'badge badge-warning badge-sm'
                  }
                >
                  {statusLabel(row.status)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}

      {rows.length ? (
        <ul
          className="space-y-2"
          aria-label="Import checklist"
          data-testid="os-plugin-import-checklist"
        >
          {rows.map((row) => {
            const state = checklistState(row.status)
            return (
              <li
                key={row.pluginId}
                className="flex items-center justify-between gap-2 text-sm"
                data-plugin-id={row.pluginId}
                data-checklist-state={state}
              >
                <span>
                  {row.name || row.pluginId}
                  {' '}
                  {state === 'connected' ? 'Connected' : state === 'needsAuth' ? 'Needs auth' : 'Missing'}
                </span>
                {state === 'connected' ? null : (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    data-testid={`os-plugin-connect-${row.pluginId}`}
                    onClick={() => void connectPlugin(row.pluginId)}
                  >
                    Connect
                  </Button>
                )}
              </li>
            )
          })}
        </ul>
      ) : null}

      {counts.enabled > 0 || counts.missing > 0 ? (
        <p className="text-xs text-base-content/55" data-testid="os-plugin-pack-summary">
          {counts.enabled} enabled
          {counts.missing ? ` · ${counts.missing} missing on this host` : ''}
        </p>
      ) : null}

      <form
        className="space-y-2"
        data-testid="os-plugin-pack-import"
        onSubmit={(event) => {
          event.preventDefault()
          void importDraft()
        }}
      >
        <Textarea
          label="Import pack"
          name="plugin-pack-import"
          size="sm"
          rows={compact ? 4 : 6}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={'web_search\nmcp:io.github.example/fetch\n\nor {"plugins":[{"pluginId":"web_search"}]}'}
          spellCheck={false}
          autoComplete="off"
        />
        <p className="text-xs text-base-content/50">
          Paste plugin ids or pack JSON. Never paste a token.
        </p>
        <Button
          type="submit"
          size="sm"
          variant="primary"
          disabled={!draft.trim() || importing}
          data-testid="os-plugin-pack-import-submit"
        >
          {importing ? (
            <Download className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <PackagePlus className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          Import pack
        </Button>
      </form>
    </div>
  )
}

function packableRows(status: AgentPluginsStatus | null): AgentPluginIdRow[] {
  if (!status) return []
  if (status.pack?.plugins?.length) return status.pack.plugins
  return status.plugins.map((row) => ({
    pluginId: row.pluginId,
    name: row.name,
    description: row.description,
  }))
}

function packableIds(status: AgentPluginsStatus | null): string[] {
  return packableRows(status).map((row) => row.pluginId)
}
