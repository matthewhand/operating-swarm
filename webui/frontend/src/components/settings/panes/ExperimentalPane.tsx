/**
 * #1230 — Experimental settings pane.
 *
 * One card per catalogue entry: name, description, architecture/status note,
 * and an explicit on/off toggle (default OFF for MVP stability). State is read
 * from / written to the shared experimentalFeatures lib, which persists to the
 * Django prefs `values` bag (`experimental_flags`) and mirrors to localStorage.
 */
import { useEffect, useState } from 'react'
import {
  EXPERIMENTAL_FEATURES,
  hydrateExperimentalFlags,
  isExperimentalFeatureEnabled,
  persistExperimentalFeature,
  type ExperimentalFeatureId,
} from '../../../lib/experimentalFeatures'
import { WebGpuProviderCard } from '../../WebGpuProviderCard'

export function ExperimentalCard({
  id,
  name,
  description,
  status,
  defaultEnabled,
  enabled,
  onToggle,
}: {
  id: ExperimentalFeatureId
  name: string
  description: string
  status: string
  defaultEnabled: boolean
  enabled: boolean
  onToggle: (next: boolean) => void
}) {
  const toggleId = `experimental-${id}`
  return (
    <div
      className="card border border-base-300 bg-base-200/40 p-4"
      data-testid={`experimental-card-${id}`}
      data-enabled={enabled ? 'true' : 'false'}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-medium">
            {name}
            <span className="ml-2 badge badge-ghost badge-xs align-middle">Experimental</span>
          </p>
          <p className="mt-1 text-sm text-base-content/70">{description}</p>
          <p className="mt-2 text-xs text-base-content/55">{status}</p>
          <p className="mt-1 text-xs text-base-content/50">
            {defaultEnabled ? 'Ships on for review' : 'Default OFF'}
          </p>
        </div>
        <label className="label cursor-pointer shrink-0 flex-col items-center gap-1" htmlFor={toggleId}>
          <input
            id={toggleId}
            type="checkbox"
            role="switch"
            className="toggle toggle-sm"
            checked={enabled}
            aria-label={`Enable ${name}`}
            data-testid={`experimental-toggle-${id}`}
            onChange={(e) => onToggle(e.target.checked)}
          />
          <span className="text-[11px] uppercase tracking-wide text-base-content/60">
            {enabled ? 'On' : 'Off'}
          </span>
        </label>
      </div>
    </div>
  )
}

export function ExperimentalPane() {
  const [flags, setFlags] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {}
    for (const feature of EXPERIMENTAL_FEATURES) {
      initial[feature.id] = isExperimentalFeatureEnabled(feature.id)
    }
    return initial
  })

  useEffect(() => {
    let cancelled = false
    void hydrateExperimentalFlags().then((merged) => {
      if (!cancelled) setFlags((prev) => ({ ...prev, ...merged }))
    })
    return () => {
      cancelled = true
    }
  }, [])

  const handleToggle = (id: ExperimentalFeatureId, next: boolean) => {
    setFlags((prev) => ({ ...prev, [id]: next }))
    void persistExperimentalFeature(id, next)
  }

  return (
    <div className="space-y-4" data-testid="experimental-pane">
      <div>
        <h4 className="text-lg font-semibold">Experimental</h4>
        <p className="mt-1 text-sm text-base-content/70">
          Bleeding-edge capabilities, off by default to keep the core chat and agent
          orchestration MVP stable. Turn one on to opt in; its affordances appear when
          the app next loads.
        </p>
      </div>

      <div className="space-y-3">
        {EXPERIMENTAL_FEATURES.map((feature) => (
          <ExperimentalCard
            key={feature.id}
            id={feature.id}
            name={feature.name}
            description={feature.description}
            status={feature.status}
            defaultEnabled={feature.defaultEnabled}
            enabled={flags[feature.id] ?? feature.defaultEnabled}
            onToggle={(next) => handleToggle(feature.id, next)}
          />
        ))}
      </div>

      {/* #1288 — the WebGPU provider surface mounts only while its flag is on. */}
      {flags.webgpu && <WebGpuProviderCard />}
    </div>
  )
}

export default ExperimentalPane
