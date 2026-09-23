/**
 * #894 — in-chat interactive provider setup card for the bootstrap
 * Admin/Support agent. Rendered inside the transcript when the bootstrap
 * reply includes a `swarm-provider-setup` fence: the first-time user picks
 * a provider preset, enters credentials, probes the connection, and
 * upgrades the Admin bot off the bootstrap provider without ever leaving
 * the chat.
 */
import { useMemo, useState, type FormEvent } from 'react'
import { Eye, EyeOff, Loader2 } from 'lucide-react'
import { useMutation } from '@tanstack/react-query'
import { Button, Input, useToast } from './DaisyUI'
import {
  PROVIDER_PRESETS,
  providerPresetById,
  type ProviderSetupCardSpec,
} from '../lib/providerSetupCard'
import { testLlmProfile, upsertLlmProfile } from '../lib/api'

export interface ProviderSetupCardProps {
  spec: ProviderSetupCardSpec
  /** Disable once the configuration has been saved (Answered state). */
  disabled?: boolean
}

type ProbeState =
  | { phase: 'idle' }
  | { phase: 'testing' }
  | { phase: 'ok'; detail: string }
  | { phase: 'error'; message: string }

export default function ProviderSetupCard({ spec, disabled = false }: ProviderSetupCardProps) {
  const { success, error: toastError } = useToast()
  const initial = providerPresetById(spec.defaultProvider || 'openai') ?? PROVIDER_PRESETS[0]
  const [providerId, setProviderId] = useState(initial.id)
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState(initial.baseUrl)
  const [model, setModel] = useState(initial.defaultModel)
  const [showKey, setShowKey] = useState(false)
  const [probe, setProbe] = useState<ProbeState>({ phase: 'idle' })
  const [configured, setConfigured] = useState(false)

  const preset = useMemo(() => providerPresetById(providerId), [providerId])

  const pickProvider = (id: string) => {
    setProviderId(id)
    const next = providerPresetById(id)
    if (next) {
      setBaseUrl(next.baseUrl)
      setModel(next.defaultModel)
    }
    setProbe({ phase: 'idle' })
  }

  const probeMutation = useMutation({
    mutationFn: async () => {
      return testLlmProfile({
        base_url: baseUrl.trim(),
        api_key_env: preset?.apiKeyEnv,
        model: model.trim() || undefined,
      })
    },
    onMutate: () => setProbe({ phase: 'testing' }),
    onSuccess: (result) => {
      const latency = result.latency_ms != null ? ` · ${result.latency_ms}ms` : ''
      if (result.ok) {
        setProbe({ phase: 'ok', detail: `Connected${latency}` })
      } else {
        setProbe({ phase: 'error', message: result.hint || result.error_class || 'Probe failed.' })
      }
    },
    onError: (err: unknown) => {
      setProbe({
        phase: 'error',
        message: err instanceof Error ? err.message : 'Probe failed.',
      })
    },
  })

  const saveMutation = useMutation({
    mutationFn: async () => {
      return upsertLlmProfile({
        id: providerId,
        model: model.trim(),
        base_url: baseUrl.trim() || undefined,
        provider: providerId,
        api_key: apiKey.trim() || undefined,
        set_default: true,
      })
    },
    onSuccess: () => {
      setConfigured(true)
      setProbe((prev) => prev)
      success(
        'Provider configured',
        `Admin bot upgraded to ${preset?.label ?? providerId} · ${model.trim()}`,
      )
    },
    onError: (err: unknown) => {
      toastError(
        'Save failed',
        err instanceof Error ? err.message : 'Could not save the provider.',
      )
    },
  })

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (disabled || configured) return
    saveMutation.mutate()
  }

  const lockInputs = disabled || configured

  return (
    <div
      className="os-provider-setup-card"
      role="form"
      aria-label="Provider setup"
      data-testid="provider-setup-card"
      data-configured={configured ? 'true' : 'false'}
    >
      {configured ? (
        <p className="os-provider-setup-configured" data-testid="provider-setup-configured">
          ✓ Connected to {preset?.label ?? providerId} · {model}
        </p>
      ) : (
        <>
          <p className="os-provider-setup-title">Configure your inference provider</p>
          <div className="os-provider-setup-groups">
            {(['cloud', 'local'] as const).map((group) => (
              <div key={group} className="os-provider-setup-group">
                <span className="os-provider-setup-group-label">
                  {group === 'cloud' ? 'Cloud' : 'Local / self-hosted'}
                </span>
                <div className="os-provider-setup-pills" role="radiogroup" aria-label={`${group} providers`}>
                  {PROVIDER_PRESETS.filter((row) => row.group === group).map((row) => (
                    <button
                      key={row.id}
                      type="button"
                      role="radio"
                      aria-checked={providerId === row.id}
                      className={`os-provider-setup-pill${providerId === row.id ? ' os-provider-setup-pill--active' : ''}`}
                      disabled={lockInputs}
                      onClick={() => pickProvider(row.id)}
                    >
                      {row.label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <form className="os-provider-setup-fields" onSubmit={onSubmit}>
            <div className="relative">
              <Input
                label={`${preset?.label ?? 'Provider'} API key`}
                name="provider-api-key"
                type={showKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                disabled={lockInputs || preset?.needsKey === false}
                autoComplete="off"
              />
              <p className="os-provider-setup-hint">
                {preset?.needsKey === false
                  ? `Not required for ${preset.label} — stored locally if provided.`
                  : `Stored as ${preset?.apiKeyEnv ?? 'API key'}.`}
              </p>
              <button
                type="button"
                className="os-provider-setup-reveal"
                aria-label={showKey ? 'Hide API key' : 'Show API key'}
                onClick={() => setShowKey((prev) => !prev)}
                disabled={lockInputs}
              >
                {showKey ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
              </button>
            </div>
            <Input
              label="Base URL"
              name="provider-base-url"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              disabled={lockInputs}
            />
            <Input
              label="Default model"
              name="provider-model"
              value={model}
              onChange={(event) => setModel(event.target.value)}
              disabled={lockInputs}
            />

            <div className="os-provider-setup-actions">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={lockInputs || probe.phase === 'testing' || !baseUrl.trim()}
                data-testid="provider-setup-test"
                onClick={() => probeMutation.mutate()}
              >
                {probe.phase === 'testing' ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Testing…
                  </>
                ) : (
                  'Test connection'
                )}
              </Button>
              <Button
                type="submit"
                variant="primary"
                size="sm"
                disabled={lockInputs || saveMutation.isPending || !model.trim()}
                data-testid="provider-setup-save"
              >
                {saveMutation.isPending ? 'Saving…' : 'Save & upgrade Admin bot'}
              </Button>
            </div>
          </form>

          {probe.phase === 'ok' ? (
            <p className="os-provider-setup-probe-ok" data-testid="provider-setup-probe-ok" role="status">
              ✓ {probe.detail}
            </p>
          ) : null}
          {probe.phase === 'error' ? (
            <p className="os-provider-setup-probe-error" data-testid="provider-setup-probe-error" role="alert">
              {probe.message}
            </p>
          ) : null}
        </>
      )}
    </div>
  )
}
