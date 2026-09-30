import { useEffect, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Pencil, Plug, Plus, Trash2 } from 'lucide-react'
import { Alert, Button, Input, Select, useToast } from './DaisyUI'
import {
  deleteMcpPlugin,
  discoverMcpPluginTools,
  fetchMcpPlugins,
  upsertMcpPlugin,
} from '../lib/api'
import { useCurrentAgent } from '../lib/currentAgent'
import AgentPluginPackPane from './AgentPluginPackPane'
import {
  MCP_SERVER_TEMPLATES,
  OPENAPI_PROXY_ARGS,
  OPENAPI_PROXY_COMMAND,
  asEnvPlaceholder,
  entryToUpsertBody,
  isEnvPlaceholder,
  isOpenApiSource,
  newMcpServerId,
  saveConfiguredMcpServers,
  serversFromApi,
  validateOpenApiWizard,
  type McpServerEntry,
  type McpServerKind,
  type McpServerSource,
} from '../lib/mcpServers'

const QUERY_KEY = ['mcp-plugins']

function emptyDraft(
  kind: McpServerKind = 'local',
  source: McpServerSource = 'generic',
): McpServerEntry {
  return {
    id: '',
    name: '',
    kind,
    source,
    enabled: true,
    command: source === 'openapi' && kind === 'local' ? OPENAPI_PROXY_COMMAND : '',
    args: source === 'openapi' && kind === 'local' ? [...OPENAPI_PROXY_ARGS] : [],
    url: '',
    openapi_spec_url: '',
    env: {},
    headers: {},
    provides: [],
    tools: [],
    note: '',
  }
}

function parseArgs(text: string): string[] {
  return text
    .split(/\s+/)
    .map((part) => part.trim())
    .filter(Boolean)
}

export default function PluginsServersPane() {
  const { success, error: toastError } = useToast()
  const queryClient = useQueryClient()
  const agent = useCurrentAgent()
  const agentId = agent?.id ?? ''
  const query = useQuery({
    queryKey: QUERY_KEY,
    queryFn: fetchMcpPlugins,
    retry: 1,
  })
  const [editing, setEditing] = useState<McpServerEntry | null>(null)
  const [kind, setKind] = useState<McpServerKind>('local')
  const [source, setSource] = useState<McpServerSource>('generic')
  const [name, setName] = useState('')
  const [command, setCommand] = useState('')
  const [argsText, setArgsText] = useState('')
  const [url, setUrl] = useState('')
  const [specSource, setSpecSource] = useState('')
  const [envName, setEnvName] = useState('')
  const [headerName, setHeaderName] = useState('')
  const [headerEnv, setHeaderEnv] = useState('')
  const [note, setNote] = useState('')
  const [originalId, setOriginalId] = useState('')

  const servers = serversFromApi(query.data)

  useEffect(() => {
    if (query.data) {
      saveConfiguredMcpServers(serversFromApi(query.data))
    }
  }, [query.data])

  const resetForm = () => {
    setEditing(null)
    setOriginalId('')
    setKind('local')
    setSource('generic')
    setName('')
    setCommand('')
    setArgsText('')
    setUrl('')
    setSpecSource('')
    setEnvName('')
    setHeaderName('')
    setHeaderEnv('')
    setNote('')
  }

  const fillForm = (entry: McpServerEntry) => {
    setEditing(entry)
    setOriginalId(entry.id)
    setKind(entry.kind)
    setSource(isOpenApiSource(entry) ? 'openapi' : 'generic')
    setName(entry.name)
    setCommand(entry.command || '')
    setArgsText((entry.args || []).join(' '))
    setUrl(entry.url || '')
    setSpecSource(entry.openapi_spec_url || '')
    const envKeys = Object.keys(entry.env || {}).filter((key) => key !== 'OPENAPI_SPEC_URL')
    setEnvName(envKeys[0] || '')
    const headerKeys = Object.keys(entry.headers || {})
    setHeaderName(headerKeys[0] || '')
    const headerVal = headerKeys[0] ? entry.headers?.[headerKeys[0]] || '' : ''
    const match = headerVal.match(/^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$/)
    setHeaderEnv(match?.[1] || '')
    setNote(entry.note || '')
  }

  const startAdd = (nextKind: McpServerKind, nextSource: McpServerSource) => {
    const draft = emptyDraft(nextKind, nextSource)
    fillForm(draft)
    setKind(nextKind)
    setSource(nextSource)
    if (nextSource === 'openapi' && nextKind === 'local') {
      setCommand(OPENAPI_PROXY_COMMAND)
      setArgsText(OPENAPI_PROXY_ARGS.join(' '))
    }
  }

  const buildEntry = (): McpServerEntry | null => {
    const trimmed = name.trim()
    if (!trimmed) return null
    const id = originalId || newMcpServerId(trimmed)
    let openapiSpec = ''
    if (source === 'openapi') {
      const check = validateOpenApiWizard({
        name: trimmed,
        kind,
        specSource,
        url,
      })
      if (!check.ok) {
        toastError(check.error, check.detail)
        return null
      }
      openapiSpec = check.specSource
    }
    const env: Record<string, string> = {}
    if ((kind === 'local' || source === 'openapi') && envName.trim()) {
      const key = envName.trim()
      if (!isEnvPlaceholder(key) && !/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
        toastError('Invalid env name', 'Use an ENV_VAR name. Never paste a token.')
        return null
      }
      env[key.replace(/^\$\{|\}$/g, '')] = asEnvPlaceholder(key) || `\${${key}}`
    }
    const headers: Record<string, string> = {}
    if (kind === 'remote' && headerName.trim()) {
      if (!headerEnv.trim() || !isEnvPlaceholder(headerEnv)) {
        toastError('Header secret must be ${VAR}', 'Never paste a token into headers.')
        return null
      }
      headers[headerName.trim()] = asEnvPlaceholder(headerEnv)
    }
    return {
      id,
      name: trimmed,
      kind,
      source,
      enabled: editing?.enabled !== false,
      command:
        kind === 'local'
          ? source === 'openapi'
            ? command.trim() || OPENAPI_PROXY_COMMAND
            : command.trim()
          : '',
      args:
        kind === 'local'
          ? source === 'openapi'
            ? parseArgs(argsText).length > 0
              ? parseArgs(argsText)
              : [...OPENAPI_PROXY_ARGS]
            : parseArgs(argsText)
          : [],
      url: kind === 'remote' ? url.trim() : '',
      openapi_spec_url: source === 'openapi' ? openapiSpec : '',
      env,
      headers,
      provides: editing?.provides || [],
      tools: editing?.tools || [],
      note: note.trim(),
    }
  }

  const saveMutation = useMutation({
    mutationFn: async (entry: McpServerEntry) => {
      if (originalId && originalId !== entry.id) {
        await deleteMcpPlugin(originalId)
      }
      return upsertMcpPlugin(entryToUpsertBody(entry))
    },
    onSuccess: (payload) => {
      queryClient.setQueryData(QUERY_KEY, payload)
      saveConfiguredMcpServers(serversFromApi(payload))
      success('MCP server saved', 'Stored in swarm_config.json mcpServers.')
      resetForm()
    },
    onError: (err: Error) => {
      toastError('Could not save MCP server', err.message)
    },
  })

  const removeMutation = useMutation({
    mutationFn: (serverName: string) => deleteMcpPlugin(serverName),
    onSuccess: (payload) => {
      queryClient.setQueryData(QUERY_KEY, payload)
      saveConfiguredMcpServers(serversFromApi(payload))
      success('MCP server removed', 'Dropped from swarm_config.json.')
    },
    onError: (err: Error) => {
      toastError('Could not remove MCP server', err.message)
    },
  })

  const enableMutation = useMutation({
    mutationFn: (entry: McpServerEntry) =>
      upsertMcpPlugin(entryToUpsertBody({ ...entry, enabled: !entry.enabled })),
    onSuccess: (payload) => {
      queryClient.setQueryData(QUERY_KEY, payload)
      saveConfiguredMcpServers(serversFromApi(payload))
    },
    onError: (err: Error) => {
      toastError('Could not update server', err.message)
    },
  })

  const discoverMutation = useMutation({
    mutationFn: (entry: McpServerEntry) =>
      discoverMcpPluginTools({
        name: entry.id,
        kind: entry.kind,
        source: entry.source,
        command: entry.command,
        args: entry.args,
        url: entry.url,
        openapi_spec_url: entry.openapi_spec_url,
        env: entry.env,
        headers: entry.headers,
      }),
    onSuccess: (payload, entry) => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY })
      const count = payload.tools.length
      success(
        count ? `Found ${count} tool${count === 1 ? '' : 's'}` : 'Connected — no tools',
        payload.tools.map((tool) => tool.name).join(', ') || `${entry.name} answered with an empty list.`,
      )
    },
    onError: (err: Error) => {
      toastError('Could not list tools', err.message)
    },
  })

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    const entry = buildEntry()
    if (!entry) return
    if (entry.kind === 'local' && !entry.command) {
      toastError('Command required', 'Local MCP servers start with a stdio command.')
      return
    }
    if (entry.kind === 'remote' && !entry.url) {
      toastError('URL required', 'Remote MCP servers need an http(s) URL.')
      return
    }
    saveMutation.mutate(entry)
  }

  const addTemplate = (template: (typeof MCP_SERVER_TEMPLATES)[number]) => {
    saveMutation.mutate({
      ...emptyDraft('local'),
      ...template,
      id: newMcpServerId(template.name),
      enabled: true,
      tools: [],
    })
  }

  return (
    <div className="space-y-4" data-testid="os-plugins-settings">
      <div>
        <h4 className="text-lg font-semibold">Plugins</h4>
        <p className="mt-1 text-sm text-base-content/70">
          Define local (stdio command), remote (URL), or OpenAPI
          (mcp-openapi-proxy) MCP servers for this host. Per-chat tool On/Off
          lives in the rail Plugins popup. Auth is <code>${'{VAR}'}</code> only
          — never paste a token. Distinct from exposing swarm as an MCP server.
        </p>
      </div>

      <AgentPluginPackPane agentId={agentId} />

      {query.isPending ? (
        <p className="text-sm text-base-content/60">Loading MCP servers…</p>
      ) : query.isError ? (
        <Alert type="warning" icon={<AlertCircle className="h-5 w-5" />}>
          <span className="text-sm">Could not load MCP servers from swarm_config.</span>
        </Alert>
      ) : servers.length === 0 && !editing ? (
        <p className="text-sm text-base-content/60">No servers configured yet.</p>
      ) : (
        <ul className="space-y-2" aria-label="Configured MCP servers">
          {servers.map((server) => (
            <li
              key={server.id}
              className="rounded-lg border border-base-300 p-3"
              data-server-id={server.id}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium">{server.name}</p>
                  <p className="truncate text-xs text-base-content/55">
                    {server.source === 'openapi'
                      ? server.kind === 'remote'
                        ? `OpenAPI proxy · ${server.url || 'MCP URL not set'}`
                        : `OpenAPI · ${server.openapi_spec_url || 'spec not set'}`
                      : server.kind === 'remote'
                        ? server.url || 'Remote URL not set'
                        : [server.command, ...(server.args || [])].filter(Boolean).join(' ') ||
                          'Local command not set'}
                  </p>
                  {(server.tools.length > 0 || server.provides.length > 0) && (
                    <ul className="mt-1 space-y-0.5" aria-label={`${server.name} tools`}>
                      {(server.tools.length > 0
                        ? server.tools
                        : server.provides.map((name) => ({ name, description: '' }))
                      ).map((tool) => (
                        <li key={tool.name} className="text-xs text-base-content/50">
                          <span className="font-mono">{tool.name}</span>
                          {tool.description ? ` — ${tool.description}` : ''}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <button
                    type="button"
                    role="switch"
                    aria-checked={server.enabled}
                    aria-label={`${server.name} ${server.enabled ? 'enabled' : 'disabled'}`}
                    className="os-plugin-toggle flex items-center gap-2"
                    onClick={() => enableMutation.mutate(server)}
                    disabled={enableMutation.isPending}
                  >
                    <input
                      type="checkbox"
                      className="toggle toggle-sm toggle-primary pointer-events-none"
                      checked={server.enabled}
                      readOnly
                      tabIndex={-1}
                      aria-hidden="true"
                    />
                    <span className="w-10 text-xs font-semibold">
                      {server.enabled ? 'On' : 'Off'}
                    </span>
                  </button>
                  <div className="flex flex-wrap justify-end gap-1">
                    <button
                      type="button"
                      className="btn btn-ghost btn-xs"
                      onClick={() => discoverMutation.mutate(server)}
                      disabled={discoverMutation.isPending}
                    >
                      Discover tools
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost btn-xs"
                      aria-label={`Edit ${server.name}`}
                      onClick={() => fillForm(server)}
                    >
                      <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                      Edit
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost btn-xs"
                      onClick={() => removeMutation.mutate(server.id)}
                      disabled={removeMutation.isPending}
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                      Remove
                    </button>
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap gap-2" aria-label="Add MCP server">
        {editing ? (
          <button type="button" className="btn btn-sm" onClick={resetForm}>
            Cancel
          </button>
        ) : (
          <>
            <button
              type="button"
              className="btn btn-sm btn-primary"
              onClick={() => startAdd('local', 'generic')}
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add: Local MCP
            </button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => startAdd('remote', 'generic')}
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add: Remote MCP
            </button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => startAdd('local', 'openapi')}
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add: OpenAPI (mcp-openapi-proxy)
            </button>
          </>
        )}
      </div>

      {editing ? (
        <form
          className="space-y-3 rounded-lg border border-base-300 p-3"
          onSubmit={handleSubmit}
          data-mcp-source={source}
        >
          {source === 'openapi' ? (
            <p className="text-sm text-base-content/70" data-testid="os-openapi-wizard-hint">
              OpenAPI (mcp-openapi-proxy). Local launches{' '}
              <code>uvx mcp-openapi-proxy</code> with <code>OPENAPI_SPEC_URL</code>.
              Remote attaches to a running proxy MCP URL. Install:{' '}
              <code>uvx mcp-openapi-proxy</code> or <code>pip install mcp-openapi-proxy</code>.
              Use env names only — never paste a token.
            </p>
          ) : null}
          <Select
            label="Kind"
            name="mcp-kind"
            value={kind}
            onChange={(event) => {
              const next = event.target.value as McpServerKind
              setKind(next)
              if (source === 'openapi' && next === 'local') {
                setCommand((current) => current || OPENAPI_PROXY_COMMAND)
                setArgsText((current) => current || OPENAPI_PROXY_ARGS.join(' '))
              }
            }}
            size="sm"
          >
            <option value="local">
              {source === 'openapi' ? 'Local stdio proxy' : 'Local command'}
            </option>
            <option value="remote">
              {source === 'openapi' ? 'Remote proxy MCP URL' : 'Remote URL'}
            </option>
          </Select>
          <Input
            label="Name"
            name="mcp-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            size="sm"
            required
            autoComplete="off"
            spellCheck={false}
          />
          {source === 'openapi' ? (
            <Input
              label={
                kind === 'local'
                  ? 'OpenAPI spec source (URL or file)'
                  : 'OpenAPI spec URL (optional)'
              }
              name="mcp-openapi-spec"
              value={specSource}
              onChange={(event) => setSpecSource(event.target.value)}
              size="sm"
              placeholder={
                kind === 'local'
                  ? 'https://example.invalid/openapi.json'
                  : 'https://example.invalid/openapi.json'
              }
              autoComplete="off"
              spellCheck={false}
            />
          ) : null}
          {kind === 'local' && source === 'generic' ? (
            <>
              <Input
                label="Command"
                name="mcp-command"
                value={command}
                onChange={(event) => setCommand(event.target.value)}
                size="sm"
                placeholder="uvx"
                autoComplete="off"
                spellCheck={false}
              />
              <Input
                label="Args"
                name="mcp-args"
                value={argsText}
                onChange={(event) => setArgsText(event.target.value)}
                size="sm"
                placeholder="mcp-server-fetch"
                autoComplete="off"
                spellCheck={false}
              />
              <Input
                label="Secret env name (optional)"
                name="mcp-env"
                value={envName}
                onChange={(event) => setEnvName(event.target.value)}
                size="sm"
                placeholder="BRAVE_API_KEY"
                autoComplete="off"
                spellCheck={false}
              />
            </>
          ) : null}
          {kind === 'local' && source === 'openapi' ? (
            <Input
              label="API auth env name (optional)"
              name="mcp-env"
              value={envName}
              onChange={(event) => setEnvName(event.target.value)}
              size="sm"
              placeholder="API_KEY"
              autoComplete="off"
              spellCheck={false}
            />
          ) : null}
          {kind === 'remote' ? (
            <>
              <Input
                label={source === 'openapi' ? 'Proxy MCP URL' : 'URL'}
                name="mcp-url"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                size="sm"
                placeholder="https://example.invalid/mcp"
                autoComplete="off"
                spellCheck={false}
              />
              <Input
                label="Auth header name (optional)"
                name="mcp-header-name"
                value={headerName}
                onChange={(event) => setHeaderName(event.target.value)}
                size="sm"
                placeholder="Authorization"
                autoComplete="off"
                spellCheck={false}
              />
              <Input
                label="Auth header env (optional)"
                name="mcp-header-env"
                value={headerEnv}
                onChange={(event) => setHeaderEnv(event.target.value)}
                size="sm"
                placeholder="MCP_TOKEN"
                autoComplete="off"
                spellCheck={false}
              />
            </>
          ) : null}
          <Input
            label="Note"
            name="mcp-note"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            size="sm"
          />
          <Button
            type="submit"
            variant="primary"
            size="sm"
            disabled={!name.trim() || saveMutation.isPending}
          >
            Save server
          </Button>
        </form>
      ) : null}

      <div>
        <p className="mb-2 text-sm font-medium">Known non-auth servers</p>
        <ul className="flex flex-wrap gap-2">
          {MCP_SERVER_TEMPLATES.map((template) => (
            <li key={template.name}>
              <button
                type="button"
                className="btn btn-ghost btn-xs"
                onClick={() => addTemplate(template)}
                disabled={saveMutation.isPending}
              >
                <Plug className="h-3.5 w-3.5" aria-hidden="true" />
                {template.name}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
