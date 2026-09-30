/**
 * #1678 — the Media tab of the agent edit pane.
 *
 * Four states, and the fourth is the point: **an error is never drawn as an
 * empty list.** "The index could not be read" and "this agent has no media" are
 * different answers, and collapsing them is how a settings surface ends up
 * reporting every agent as unconfigured. Only the empty state — a real,
 * successful answer — is allowed to say "nothing here", and a failed *forget*
 * is its own state that leaves the item in the list instead of optimistically
 * dropping it.
 *
 * Bytes are never addressed here. Items are listed by attachment id, named by
 * their display basename, and previewed through the existing same-origin
 * content route. A server filesystem path is never rendered — the user cannot
 * act on one.
 *
 * Only *forget* is offered. Forget drops the metadata row and leaves the bytes
 * for the retention sweep, because a stored message may still reference the id.
 * See the design note on issue #1678.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { ExternalLink, FileWarning, ImageOff, Loader2, RotateCw, Trash2 } from 'lucide-react'
import { Alert, Button, ConfirmModal } from './DaisyUI'
import {
  agentMediaContentPath,
  fetchAgentMedia,
  forgetAgentMedia,
  type AgentMediaItem,
} from '../lib/agentMedia'

export interface AgentMediaPanelProps {
  agentId: string
  /** The editor keeps inactive panels mounted (#1127). The index is only read
   *  when the tab is actually selected, so opening the editor on Identity does
   *  not spend a request on media nobody is looking at. */
  active?: boolean
}

type MediaState =
  | { status: 'loading' }
  | { status: 'error'; error: string }
  | { status: 'ready'; items: AgentMediaItem[] }

function errorText(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message
  if (typeof error === 'string' && error.trim()) return error
  return 'The media index did not answer.'
}

function formatSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return 'unknown size'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatWhen(iso: string | null): string {
  if (!iso) return ''
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return ''
  return parsed.toLocaleString()
}

export function AgentMediaPanel({ agentId, active = true }: AgentMediaPanelProps) {
  const [state, setState] = useState<MediaState>({ status: 'loading' })
  const [pendingForget, setPendingForget] = useState<AgentMediaItem | null>(null)
  const [forgetting, setForgetting] = useState(false)
  const [forgetError, setForgetError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    if (!agentId || !active) return
    let cancelled = false
    setState({ status: 'loading' })
    void fetchAgentMedia(agentId)
      .then((items) => {
        if (cancelled) return
        setState({ status: 'ready', items })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        // Deliberately NOT an empty list.
        setState({ status: 'error', error: errorText(error) })
      })
    return () => {
      cancelled = true
    }
  }, [agentId, active, retry])

  const items = useMemo(
    () => (state.status === 'ready' ? state.items : []),
    [state],
  )

  const confirmForget = useCallback(async () => {
    const target = pendingForget
    if (!target) return
    setForgetting(true)
    setForgetError(null)
    try {
      await forgetAgentMedia(agentId, target.id)
      setPendingForget(null)
      setState((prev) =>
        prev.status === 'ready'
          ? { status: 'ready', items: prev.items.filter((item) => item.id !== target.id) }
          : prev,
      )
    } catch (error) {
      // Swallow rather than re-throw: `ConfirmModal` renders its own copy of a
      // rejection and would leave the dialog parked on screen. Closing the
      // dialog and putting the reason next to the list — where the item that
      // is still there can be seen — is the more useful placement, and the item
      // is NOT dropped, because dropping it would be a lie.
      setPendingForget(null)
      setForgetError(errorText(error))
    } finally {
      setForgetting(false)
    }
  }, [agentId, pendingForget])

  if (!agentId) {
    return (
      <div className="space-y-3" data-testid="agent-media-panel">
        <p className="text-sm text-base-content/70" data-testid="agent-media-unscoped">
          Media is listed per agent seat. This editor has no agent scope, so there is nothing to
          list.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-3" data-testid="agent-media-panel">
      <p className="text-sm text-base-content/70">
        Every file this agent received or attached in its chats. Items are stored on the Swarm
        host — this list shows names, never server paths.
      </p>

      {state.status === 'loading' ? (
        <div
          className="flex items-center gap-2 text-sm text-base-content/70"
          data-testid="agent-media-loading"
          role="status"
          aria-live="polite"
        >
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          Loading this agent&rsquo;s media…
        </div>
      ) : null}

      {state.status === 'error' ? (
        <div className="space-y-2" data-testid="agent-media-error">
          <Alert type="error" icon={<FileWarning className="h-5 w-5" />}>
            <strong>Media list unavailable.</strong> The index for this agent could not be read, so
            nothing below is being claimed about what it has: {state.error}
          </Alert>
          <Button type="button" size="sm" variant="outline" onClick={() => setRetry((n) => n + 1)}>
            <RotateCw className="h-4 w-4" aria-hidden="true" />
            Retry
          </Button>
        </div>
      ) : null}

      {state.status === 'ready' && items.length === 0 ? (
        <div
          className="rounded-box border border-dashed border-base-300 p-4 text-sm text-base-content/70"
          data-testid="agent-media-empty"
        >
          <p className="font-medium text-base-content/80">No media yet</p>
          <p className="mt-1">
            Nothing has been attached to this agent&rsquo;s conversations. Files you attach in the
            composer, and files its tools attach, show up here.
          </p>
        </div>
      ) : null}

      {state.status === 'ready' && items.length > 0 ? (
        <div className="space-y-2">
          <p className="text-xs text-base-content/60" data-testid="agent-media-count">
            {items.length} {items.length === 1 ? 'item' : 'items'}
          </p>
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2" data-testid="agent-media-list">
            {items.map((item) => {
              const contentPath = agentMediaContentPath(item.id)
              return (
                <li
                  key={item.id}
                  className="os-agent-media-item flex gap-3 rounded-box border border-base-300 p-2"
                  data-testid="agent-media-item"
                  data-media-id={item.id}
                >
                  {item.is_image ? (
                    <img
                      className="os-agent-media-thumb h-14 w-14 shrink-0 rounded-md object-cover"
                      src={contentPath}
                      alt={item.name}
                      loading="lazy"
                    />
                  ) : (
                    <span
                      className="os-agent-media-thumb flex h-14 w-14 shrink-0 items-center justify-center rounded-md bg-base-200"
                      aria-hidden="true"
                    >
                      <ImageOff className="h-5 w-5 text-base-content/50" />
                    </span>
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium" title={item.name}>
                      {item.name}
                    </p>
                    <p className="text-xs text-base-content/60">
                      {item.content_type || 'unknown type'} · {formatSize(item.size)} ·{' '}
                      {item.source === 'agent' ? 'attached by agent' : 'from you'}
                    </p>
                    {formatWhen(item.created_at) ? (
                      <p className="text-xs text-base-content/50">{formatWhen(item.created_at)}</p>
                    ) : null}
                    <div className="mt-1 flex flex-wrap items-center gap-1">
                      <a
                        className="btn btn-ghost btn-xs"
                        href={contentPath}
                        target="_blank"
                        rel="noreferrer"
                        aria-label={`Open ${item.name} in a new tab`}
                      >
                        <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                        Open
                      </a>
                      <Button
                        type="button"
                        size="xs"
                        variant="ghost"
                        aria-label={`Forget ${item.name}`}
                        onClick={() => {
                          setForgetError(null)
                          setPendingForget(item)
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                        Forget
                      </Button>
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
      ) : null}

      {forgetError ? (
        <Alert type="error" icon={<FileWarning className="h-5 w-5" />}>
          <span data-testid="agent-media-forget-error">
            <strong>Nothing was forgotten.</strong> The item is still listed, because the delete
            did not succeed: {forgetError}
          </span>
        </Alert>
      ) : null}

      <ConfirmModal
        isOpen={pendingForget !== null}
        onClose={() => {
          if (!forgetting) setPendingForget(null)
        }}
        title="Forget this media item?"
        confirmText="Forget it"
        confirmVariant="warning"
        onConfirm={confirmForget}
      >
        <p>
          <strong>{pendingForget?.name}</strong> will be removed from this agent&rsquo;s media list
          and its database record deleted.
        </p>
        <p className="mt-2">
          The file itself is <em>not</em> deleted from disk. It becomes unreachable through the
          app and is reclaimed later by the retention sweep. Keeping the bytes is deliberate: a
          chat message may still reference this file, and removing it would leave a broken message
          behind.
        </p>
      </ConfirmModal>
    </div>
  )
}

export default AgentMediaPanel
