import { useState } from 'react'
import type { Agent } from '../../types/agent'
import type { CliCatalogEntry, LlmProfileEntry, RemoteFrameworkEntry } from '../../lib/agent-api'
import { CLI_STARTER_NAMES } from '../../lib/starter-agents'
import { remoteKindLabel } from '../../lib/remoteKinds'
import { agentTypeOf, type RemoteMemberOption } from '../../lib/agent-types'

const CUSTOM_MODEL = '__custom__'

const FALLBACK_REMOTE_FRAMEWORKS: { id: string; name: string }[] = [
  { id: 'openmausbot', name: 'OpenMausBot' },
  { id: 'hermes', name: 'Hermes' },
  { id: 'dsh', name: 'DeepSeek Harness' },
]

export function cliDropdownEntries(clis: CliCatalogEntry[]): CliCatalogEntry[] {
  const byName = new Map(clis.map((c) => [c.name, c]))
  const preferred: CliCatalogEntry[] = CLI_STARTER_NAMES.map((name) => {
    const known = byName.get(name)
    return known || { name, executable: name, installed: false, models: [] }
  })
  const rest = clis.filter((c) => !(CLI_STARTER_NAMES as readonly string[]).includes(c.name))
  return [...preferred, ...rest]
}

export function defaultBackendFor(agent: Agent | undefined): string {
  if (!agent) return 'api'
  const agentType = agentTypeOf(agent)
  if (agentType === 'cli' && agent.cli) return `cli:${agent.cli}`
  if (agentType === 'remote') return 'remote'
  return 'api'
}

export function backendRouteParams(
  value: string,
  llmProfile?: string,
  cliModel?: string,
  remoteId?: string,
  blueprintId?: string,
  framework?: string,
): Record<string, string> {
  if (value.startsWith('cli:')) {
    const params: Record<string, string> = { backend: 'cli', cli: value.slice(4) }
    const model = (cliModel || '').trim()
    if (model) params.cli_model = model
    return params
  }
  if (value === 'remote') {
    const params: Record<string, string> = { backend: 'remote' }
    const id = (remoteId || '').trim()
    if (id) {
      params.remote_id = id
      params.target = id
      params.model = id
    }
    const fw = (framework || '').trim()
    if (fw) params.framework = fw
    return params
  }
  const params: Record<string, string> = { backend: 'api' }
  if (llmProfile) params.llm_profile = llmProfile
  const blueprint = (blueprintId || '').trim()
  if (blueprint) params.blueprint = blueprint
  return params
}

interface BackendSelectProps {
  agent: Agent
  value: string
  clis: CliCatalogEntry[]
  onChange: (value: string) => void
  llmProfiles?: LlmProfileEntry[]
  llmValue?: string
  defaultLlm?: string
  onLlmChange?: (value: string) => void
  cliModel?: string
  onCliModelChange?: (value: string) => void
  remoteMembers?: RemoteMemberOption[]
  remoteMember?: string
  onRemoteMemberChange?: (value: string) => void
  blueprints?: { id: string; name: string }[]
  blueprintValue?: string
  onBlueprintChange?: (value: string) => void
  remoteFrameworks?: Pick<RemoteFrameworkEntry, 'id' | 'name'>[]
  remoteFramework?: string
  onRemoteFrameworkChange?: (value: string) => void
}

/** DaisyUI select: API (LiteLLM) vs installed CLI, plus CLI model / custom id. */
export function BackendSelect({
  agent,
  value,
  clis,
  onChange,
  llmProfiles = [],
  llmValue = '',
  defaultLlm = '',
  onLlmChange,
  cliModel = '',
  onCliModelChange,
  remoteMembers = [],
  remoteMember = '',
  onRemoteMemberChange,
  blueprints = [],
  blueprintValue = '',
  onBlueprintChange,
  remoteFrameworks = [],
  remoteFramework = '',
  onRemoteFrameworkChange,
}: BackendSelectProps) {
  const agentType = agentTypeOf(agent)
  const cliChoices = agentType === 'cli' ? cliDropdownEntries(clis) : []
  const remoteLabel = agent.framework
    ? `Remote · ${remoteKindLabel(agent.framework)}`
    : 'Remote'
  const cliSelected = value.startsWith('cli:')
  const showLlm = agentType === 'api' && !!onLlmChange
  const showBlueprint = agentType === 'api' && !!onBlueprintChange
  const showCliModel = agentType === 'cli' && !!onCliModelChange
  const showRemote = agentType === 'remote' && !!onRemoteMemberChange
  const showRemoteFramework = agentType === 'remote' && !!onRemoteFrameworkChange
  const frameworkOptions = remoteFrameworks.length > 0 ? remoteFrameworks : FALLBACK_REMOTE_FRAMEWORKS
  const frameworkValue = remoteFramework || agent.framework || frameworkOptions[0]?.id || ''
  const defaultLabel = defaultLlm || 'auxiliary'
  const cliName = cliSelected ? value.slice(4) : (agent.cli || '')
  const cliMeta = clis.find((c) => c.name === cliName)
  const knownModels = cliMeta?.models || []
  const trimmedModel = cliModel.trim()
  const modelIsKnown = trimmedModel !== '' && knownModels.includes(trimmedModel)
  const [customOpen, setCustomOpen] = useState(
    () => trimmedModel !== '' && !knownModels.includes(trimmedModel),
  )
  const showCustom = !modelIsKnown && (customOpen || trimmedModel !== '')
  const modelSelectValue = showCustom ? CUSTOM_MODEL : trimmedModel
  const remoteSelectValue = remoteMember || ''

  const showBackendSelect = agentType !== 'remote' || !showRemoteFramework

  return (
    <div className="flex items-center gap-1 min-w-0 flex-wrap">
      {showBackendSelect && (
      <label className="flex items-center gap-1 min-w-0">
        <span className="sr-only">Model backend</span>
        <select
          className="select select-xs select-bordered h-7 min-h-0 max-w-[11rem] font-medium"
          aria-label="Model backend"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          title="Run this bot on LiteLLM or an installed CLI"
        >
          {agentType === 'api' && <option value="api">LiteLLM</option>}
          {agentType === 'remote' && (
            <option value="remote">{remoteLabel}</option>
          )}
          {agentType === 'cli' && (
            <optgroup label="CLI">
              {cliChoices.map((c) => (
                <option key={c.name} value={`cli:${c.name}`}>
                  CLI · {c.name}{c.installed ? '' : ' (not installed)'}
                </option>
              ))}
            </optgroup>
          )}
        </select>
      </label>
      )}
      {showBlueprint && (
        <label className="flex items-center gap-1 min-w-0">
          <span className="sr-only">Blueprint</span>
          <select
            className="select select-xs select-bordered h-7 min-h-0 max-w-[14rem] font-medium"
            aria-label="Blueprint"
            value={blueprintValue}
            onChange={(e) => onBlueprintChange?.(e.target.value)}
            title="Coded BlueprintBase team to run for this API agent"
          >
            <option value="">Blueprint…</option>
            {blueprints.map((bp) => (
              <option key={bp.id} value={bp.id}>
                {bp.name || bp.id}
              </option>
            ))}
          </select>
        </label>
      )}
      {showLlm && (
        <label className="flex items-center gap-1 min-w-0">
          <span className="sr-only">LLM profile</span>
          <select
            className="select select-xs select-bordered h-7 min-h-0 max-w-[12rem] font-medium"
            aria-label="LLM profile"
            value={llmValue}
            onChange={(e) => onLlmChange?.(e.target.value)}
            title="Override the default LiteLLM model for this agent"
          >
            <option value="">LiteLLM · {defaultLabel} (default)</option>
            {llmProfiles.map((p) => (
              <option key={p.name} value={p.name}>
                LiteLLM · {p.model || p.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {showCliModel && (
        <>
          <label className="flex items-center gap-1 min-w-0">
            <span className="sr-only">CLI model</span>
            <select
              className="select select-xs select-bordered h-7 min-h-0 max-w-[12rem] font-medium"
              aria-label="CLI model"
              value={modelSelectValue}
              onChange={(e) => {
                const next = e.target.value
                if (next === CUSTOM_MODEL) {
                  setCustomOpen(true)
                  if (modelIsKnown || !trimmedModel) onCliModelChange?.('')
                  return
                }
                setCustomOpen(false)
                onCliModelChange?.(next)
              }}
              title={
                cliMeta?.model_flag
                  ? `Pin ${cliName} with ${cliMeta.model_flag} <model>, or type a custom id`
                  : `Model id passed to ${cliName || 'this CLI'} (custom string always allowed)`
              }
            >
              <option value="">
                {cliName ? `${cliName} default` : 'CLI default'}
              </option>
              {knownModels.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
              <option value={CUSTOM_MODEL}>Custom…</option>
            </select>
          </label>
          {showCustom && (
            <label className="flex items-center gap-1 min-w-0">
              <span className="sr-only">Custom CLI model</span>
              <input
                className="input input-xs input-bordered h-7 min-h-0 w-[9rem] font-medium"
                aria-label="Custom CLI model"
                value={cliModel}
                onChange={(e) => onCliModelChange?.(e.target.value)}
                placeholder="model id"
                title="Any model id the CLI accepts"
              />
            </label>
          )}
        </>
      )}
      {showRemoteFramework && (
        <label className="flex items-center gap-1 min-w-0">
          <span className="sr-only">Remote framework</span>
          <select
            className="select select-xs select-bordered h-7 min-h-0 max-w-[14rem] font-medium"
            aria-label="Remote framework"
            value={frameworkValue}
            onChange={(e) => onRemoteFrameworkChange?.(e.target.value)}
            title="Remote team to talk to"
          >
            {frameworkOptions.map((f) => (
              <option key={f.id} value={f.id}>
                {remoteKindLabel(f.id, f.name || f.id)}
              </option>
            ))}
          </select>
        </label>
      )}
      {showRemote && (
        <label className="flex items-center gap-1 min-w-0">
          <span className="sr-only">Remote member</span>
          <select
            className="select select-xs select-bordered h-7 min-h-0 max-w-[14rem] font-medium"
            aria-label="Remote member"
            value={remoteSelectValue}
            onChange={(e) => onRemoteMemberChange?.(e.target.value)}
            title="Child agent on this remote team"
          >
            {remoteMembers.length === 0 && (
              <option value="">
                {agent.framework ? `${agent.framework} default` : 'Remote default'}
              </option>
            )}
            {remoteMembers.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  )
}
