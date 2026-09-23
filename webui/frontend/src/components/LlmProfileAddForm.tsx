import { useId, useState } from 'react'
import { Button, Input, Select, useToast, LoadingSpinner } from './DaisyUI'
import { patchConfigSection, testLlmProfile } from '../lib/api'
import {
  LLM_PROFILE_PROVIDERS,
  buildLlmProfileEntry,
  probeHint,
  probeStateFromResult,
  type LlmProbeState,
} from '../lib/llmProfiles'

export default function LlmProfileAddForm({
  className = '',
  onCancel,
  onSaved,
}: {
  className?: string
  onCancel: () => void
  onSaved: () => void | Promise<void>
}) {
  const { success, error: toastError } = useToast()
  const modelListId = `llm-profile-models-${useId().replace(/:/g, '')}`
  const [profileName, setProfileName] = useState('')
  const [profileProvider, setProfileProvider] = useState('openai')
  const [profileModel, setProfileModel] = useState('')
  const [profileBaseUrl, setProfileBaseUrl] = useState('')
  const [profileKeyEnv, setProfileKeyEnv] = useState('OPENAI_API_KEY')
  const [profileTemperature, setProfileTemperature] = useState('')
  const [profileMaxTokens, setProfileMaxTokens] = useState('')
  const [profileTimeout, setProfileTimeout] = useState('')
  const [addAdvancedOpen, setAddAdvancedOpen] = useState(false)
  const [probeState, setProbeState] = useState<LlmProbeState>('idle')
  const [probeLatency, setProbeLatency] = useState<number | null>(null)
  const [probeMessage, setProbeMessage] = useState('')
  const [discoveredModels, setDiscoveredModels] = useState<string[]>([])

  const runProbe = async (action: 'test' | 'list_models' = 'test') => {
    const baseUrl = profileBaseUrl.trim()
    if (!baseUrl) {
      setProbeState('error')
      setProbeMessage(probeHint('invalid'))
      return
    }
    setProbeState('testing')
    setProbeMessage('')
    try {
      const result = await testLlmProfile({
        base_url: baseUrl,
        api_key_env: profileKeyEnv.trim() || undefined,
        model: profileModel.trim() || undefined,
        action,
      })
      const models = result.models ?? []
      if (models.length) setDiscoveredModels(models)
      const next = probeStateFromResult(result)
      setProbeState(next)
      setProbeLatency(typeof result.latency_ms === 'number' ? result.latency_ms : null)
      setProbeMessage(
        next === 'ok'
          ? `Connected · ${result.latency_ms}ms`
          : result.hint || probeHint(result.error_class),
      )
    } catch (err) {
      setProbeState('error')
      setProbeLatency(null)
      setProbeMessage(err instanceof Error ? err.message : 'Probe failed.')
    }
  }

  const statusClass =
    probeState === 'ok'
      ? 'text-success'
      : probeState === 'warn'
        ? 'text-warning'
        : probeState === 'error'
          ? 'text-error'
          : 'text-base-content/70'

  return (
    <div data-testid="llm-profile-add-overlay" className={className}>
      <p className="text-sm font-medium">Add LLM profile</p>
      <Input
        label="Name"
        name="llm-profile-id"
        value={profileName}
        onChange={(event) => setProfileName(event.target.value)}
        placeholder="local"
        autoComplete="off"
        spellCheck={false}
      />
      <Select
        label="Provider"
        name="llm-profile-provider"
        value={profileProvider}
        onChange={(event) => setProfileProvider(event.target.value)}
        size="sm"
      >
        {LLM_PROFILE_PROVIDERS.map((id) => (
          <option key={id} value={id}>
            {id}
          </option>
        ))}
      </Select>
      <Input
        label="Model"
        name="llm-profile-model"
        list={modelListId}
        value={profileModel}
        onChange={(event) => setProfileModel(event.target.value)}
        placeholder="gpt-4o-mini"
        autoComplete="off"
        spellCheck={false}
      />
      <datalist id={modelListId} data-testid="llm-profile-model-options">
        {discoveredModels.map((id) => (
          <option key={id} value={id} />
        ))}
      </datalist>
      <Input
        label="API key env"
        name="llm-profile-key-env"
        value={profileKeyEnv}
        onChange={(event) => setProfileKeyEnv(event.target.value)}
        placeholder="OPENAI_API_KEY"
        autoComplete="off"
        spellCheck={false}
      />
      <Input
        label="Base URL"
        name="llm-profile-base"
        value={profileBaseUrl}
        onChange={(event) => setProfileBaseUrl(event.target.value)}
        placeholder="https://api.openai.com/v1"
        autoComplete="off"
        spellCheck={false}
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          loading={probeState === 'testing'}
          disabled={!profileBaseUrl.trim()}
          onClick={() => void runProbe('test')}
        >
          Test connection
        </Button>
        <div
          data-testid="llm-profile-probe-status"
          data-state={probeState}
          className={`flex items-center gap-2 text-sm ${statusClass}`}
          role="status"
        >
          {probeState === 'testing' ? (
            <>
              <LoadingSpinner size="xs" aria-label="Testing connection" />
              <span>Testing…</span>
            </>
          ) : probeState === 'idle' ? null : (
            <span>
              {probeMessage}
              {probeState === 'ok' && probeLatency != null && !probeMessage.includes('ms')
                ? ` · ${probeLatency}ms`
                : ''}
            </span>
          )}
        </div>
      </div>
      <button
        type="button"
        className="text-sm font-medium underline-offset-2 hover:underline"
        aria-expanded={addAdvancedOpen}
        aria-controls="llm-profile-add-advanced"
        onClick={() => setAddAdvancedOpen((open) => !open)}
      >
        Advanced
      </button>
      {addAdvancedOpen ? (
        <div id="llm-profile-add-advanced" data-testid="llm-profile-add-advanced" className="space-y-3">
          <Input
            label="Temperature"
            name="llm-profile-temperature"
            value={profileTemperature}
            onChange={(event) => setProfileTemperature(event.target.value)}
            placeholder="0.2"
            autoComplete="off"
            spellCheck={false}
          />
          <Input
            label="Max tokens"
            name="llm-profile-max-tokens"
            value={profileMaxTokens}
            onChange={(event) => setProfileMaxTokens(event.target.value)}
            placeholder="4096"
            autoComplete="off"
            spellCheck={false}
          />
          <Input
            label="Timeout (sec)"
            name="llm-profile-timeout"
            value={profileTimeout}
            onChange={(event) => setProfileTimeout(event.target.value)}
            placeholder="60"
            autoComplete="off"
            spellCheck={false}
          />
        </div>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!profileName.trim() || !profileModel.trim()}
          onClick={async () => {
            try {
              await patchConfigSection('llm', {
                upsert: {
                  [profileName.trim()]: buildLlmProfileEntry({
                    provider: profileProvider,
                    model: profileModel,
                    apiKeyEnv: profileKeyEnv,
                    baseUrl: profileBaseUrl,
                    temperature: profileTemperature,
                    maxTokens: profileMaxTokens,
                    timeoutSec: profileTimeout,
                  }),
                },
              })
              success('LLM profile saved', 'Named profile stored in swarm_config.json llm.')
              await onSaved()
            } catch (err) {
              toastError(
                'Could not save LLM profile',
                err instanceof Error ? err.message : 'Request failed.',
              )
            }
          }}
        >
          Save profile
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  )
}
