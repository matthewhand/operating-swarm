/** #856 slice B — SystemPane (moved verbatim from SettingsSheet.tsx). */
import { useId } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle, HardDrive } from 'lucide-react'
import { Alert } from '../.././DaisyUI'
import EnvOverrideBadge from '../.././EnvOverrideBadge'
import {
  EMPTY_LOCAL_STORE,
  fetchConfigOwnership,
  fetchLocalStore,
} from '../../../lib/api'
import { formatStoreSize } from '../../../lib/localStore'

export function SystemPane() {
  const headingId = useId()
  const storeQuery = useQuery({
    queryKey: ['settings-local-store'],
    queryFn: fetchLocalStore,
    retry: false,
    staleTime: 0,
    refetchOnMount: 'always',
  })
  const ownershipQuery = useQuery({
    queryKey: ['settings-config-ownership'],
    queryFn: fetchConfigOwnership,
    retry: false,
  })
  const facts = storeQuery.data || EMPTY_LOCAL_STORE
  const sizeLabel =
    facts.created && facts.size_bytes > 0
      ? facts.size_label || formatStoreSize(facts.size_bytes)
      : formatStoreSize(facts.size_bytes)
  const location = facts.path?.trim() || 'not created yet'

  return (
    <section id="os-system-store" aria-labelledby={headingId} className="space-y-4">
      <div>
        <h4 id={headingId} className="text-lg font-semibold">
          System
        </h4>
        <p className="mt-1 text-sm text-base-content/70">
          Local database on this machine. Read-only facts refresh when you open
          this section.
        </p>
      </div>
      {storeQuery.isPending ? (
        <p className="text-sm text-base-content/60">Loading local database…</p>
      ) : storeQuery.isError ? (
        <div className="space-y-3" data-testid="system-store-error">
          <Alert type="error" icon={<AlertCircle className="h-5 w-5" />}>
            <span className="text-sm">
              Failed to load local database facts. Check local daemon connection.
            </span>
          </Alert>
          <button
            type="button"
            className="btn btn-sm btn-outline"
            onClick={() => void storeQuery.refetch()}
          >
            Retry
          </button>
        </div>
      ) : (
        <dl className="space-y-3 text-sm">
          <div className="rounded-lg border border-base-300 bg-base-200/60 px-3 py-2">
            <dt className="text-xs uppercase tracking-wide text-base-content/60">Size</dt>
            <dd className="mt-0.5 font-medium">{sizeLabel}</dd>
          </div>
          <div className="rounded-lg border border-base-300 bg-base-200/60 px-3 py-2">
            <dt className="text-xs uppercase tracking-wide text-base-content/60">Location</dt>
            <dd className="mt-0.5 break-all font-mono text-xs">{location}</dd>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-base-300 bg-base-200/60 px-3 py-2">
              <dt className="text-xs uppercase tracking-wide text-base-content/60">Conversations</dt>
              <dd className="mt-0.5 font-medium">{facts.conversation_count}</dd>
            </div>
            <div className="rounded-lg border border-base-300 bg-base-200/60 px-3 py-2">
              <dt className="text-xs uppercase tracking-wide text-base-content/60">Messages</dt>
              <dd className="mt-0.5 font-medium">{facts.message_count}</dd>
            </div>
          </div>
        </dl>
      )}
      <p className="text-xs text-base-content/50">
        <HardDrive className="mr-1 inline h-3.5 w-3.5" aria-hidden="true" />
        Stored on this machine. No remote host.
      </p>

      {ownershipQuery.data?.object === 'config_ownership' ? (
        <div className="space-y-3 border-t border-base-200 pt-4" data-testid="config-coverage">
          <h5 className="text-sm font-semibold">Config coverage</h5>
          <p className="text-xs text-base-content/70">
            Decision: <strong>{ownershipQuery.data.decision}</strong> — {ownershipQuery.data.note}
          </p>
          {ownershipQuery.data.force_env ? (
            <EnvOverrideBadge
              badge={{
                kind: 'forced',
                label: `Forced by env ${ownershipQuery.data.force_env_var} (read-only)`,
                env_var: ownershipQuery.data.force_env_var,
                forced: true,
                editable: false,
              }}
            />
          ) : null}
          <p className="text-xs font-medium text-base-content/70">Advanced / not a dedicated pane</p>
          <ul className="list-disc space-y-1 pl-5 text-xs text-base-content/70">
            {(ownershipQuery.data.advanced_sections || []).map((key) => (
              <li key={key}>
                <code>{key}</code> — write via <code>/v1/config/sections/{key}/</code> or swarm-cli
              </li>
            ))}
          </ul>
          <p className="text-xs font-medium text-base-content/70">Secrets · env-only</p>
          <ul className="list-disc space-y-1 pl-5 text-xs text-base-content/70">
            {(ownershipQuery.data.inventory || [])
              .filter((row) => row.partition === 'env_only')
              .map((row) => (
                <li key={row.key}>
                  <code>{row.key}</code> — {row.notes}
                </li>
              ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}
