import { useEffect, useRef, useState } from 'react'
import { Server, Settings2 } from 'lucide-react'
import { probeRemoteHealth, type RemoteConnection } from '../lib/api'
import { remoteDisplayName } from '../lib/remotesCatalog'
import {
  CHAT_CONNECTION_EVENT,
  getChatConnection,
  type ChatConnectionStatus,
} from '../lib/chatConnection'

export interface RemoteSessionsPopupProps {
  isOpen: boolean
  onClose: () => void
  remotes: RemoteConnection[]
  onOpenSettingsRemotes: () => void
}

/** Strip sensitive authentication query params from remote URLs (REQ-118). */
export function cleanRemoteUrl(rawUrl: string): string {
  try {
    const parsed = new URL(rawUrl)
    const sensitive = ['token', 'api_key', 'apikey', 'key', 'auth', 'auth_token', 'password', 'secret']
    for (const param of Array.from(parsed.searchParams.keys())) {
      if (sensitive.some((s) => param.toLowerCase().includes(s))) {
        parsed.searchParams.delete(param)
      }
    }
    return parsed.toString()
  } catch {
    return rawUrl
  }
}

export function isBrowsableRemote(remote: RemoteConnection): boolean {
  const target = (remote.ui_url?.trim() || remote.base_url?.trim()) ?? ''
  return Boolean(target && /^https?:\/\//i.test(target))
}

export default function RemoteSessionsPopup({
  isOpen,
  onClose,
  remotes,
  onOpenSettingsRemotes,
}: RemoteSessionsPopupProps) {
  const popupRef = useRef<HTMLDivElement | null>(null)
  const [healthMap, setHealthMap] = useState<Record<string, 'pending' | 'ok' | 'failed'>>({})
  const [wsStatus, setWsStatus] = useState<ChatConnectionStatus>(() => getChatConnection())

  const browsable = remotes.filter(isBrowsableRemote)

  useEffect(() => {
    if (!isOpen) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        event.stopPropagation()
        onClose()
      }
    }
    const handlePointerDown = (event: PointerEvent) => {
      if (popupRef.current && !popupRef.current.contains(event.target as Node)) {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    window.addEventListener('pointerdown', handlePointerDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('pointerdown', handlePointerDown)
    }
  }, [isOpen, onClose])

  useEffect(() => {
    if (!isOpen) return
    const handleStatus = (event: Event) => {
      const customEvent = event as CustomEvent<ChatConnectionStatus>
      if (customEvent.detail) {
        setWsStatus(customEvent.detail)
      }
    }
    window.addEventListener(CHAT_CONNECTION_EVENT, handleStatus)
    return () => {
      window.removeEventListener(CHAT_CONNECTION_EVENT, handleStatus)
    }
  }, [isOpen])

  useEffect(() => {
    if (!isOpen || browsable.length === 0) return
    let active = true

    const initialMap: Record<string, 'pending' | 'ok' | 'failed'> = {}
    for (const r of browsable) {
      initialMap[r.id] = 'pending'
    }
    setHealthMap(initialMap)

    for (const remote of browsable) {
      probeRemoteHealth(remote.id)
        .then((res) => {
          if (!active) return
          setHealthMap((prev) => ({
            ...prev,
            [remote.id]: res.ok ? 'ok' : 'failed',
          }))
        })
        .catch(() => {
          if (!active) return
          setHealthMap((prev) => ({
            ...prev,
            [remote.id]: 'failed',
          }))
        })
    }

    return () => {
      active = false
    }
  }, [isOpen, remotes])

  if (!isOpen) return null

  const localWsDown = wsStatus === 'closed' || wsStatus === 'failed'

  return (
    <div
      ref={popupRef}
      role="menu"
      aria-label="Remote sessions"
      className="absolute bottom-full left-0 mb-2 w-64 rounded-box border border-base-300 bg-base-100 shadow-xl z-50 overflow-hidden"
      data-testid="remote-sessions-popup"
    >
      <div className="p-2">
        <div className="px-2 py-1 font-semibold text-base-content/80 text-[11px] uppercase tracking-wider flex items-center justify-between">
          <span>Remote sessions</span>
          <span
            className="flex items-center gap-1 text-[10px] lowercase font-normal tracking-normal text-base-content/60"
            data-testid="popup-local-status"
          >
            <span className="relative inline-flex items-center">
              <Server className="h-3 w-3 text-base-content/50" aria-hidden="true" />
              {localWsDown && (
                <span
                  data-testid="popup-local-health-dot"
                  className="absolute -top-0.5 -right-0.5 h-1.5 w-1.5 rounded-full bg-error ring-1 ring-base-100"
                />
              )}
            </span>
            <span>local</span>
          </span>
        </div>
        {browsable.length === 0 ? (
          <div className="px-2 py-2 text-xs text-base-content/65" data-testid="remotes-empty-state">
            <p>No remotes configured</p>
            <button
              type="button"
              className="mt-1 text-primary hover:underline block text-left"
              onClick={() => {
                onClose()
                onOpenSettingsRemotes()
              }}
            >
              Configure in Settings
            </button>
          </div>
        ) : (
          <ul className="menu menu-xs p-0 gap-0.5" role="none">
            {browsable.map((remote) => {
              const raw = remote.ui_url?.trim() || remote.base_url?.trim() || ''
              const url = cleanRemoteUrl(raw)
              const label = remoteDisplayName(remote)
              const isFailed = healthMap[remote.id] === 'failed'
              return (
                <li key={remote.id} role="none">
                  <a
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    role="menuitem"
                    className="flex items-start gap-2 py-1.5 px-2 rounded hover:bg-base-200"
                    onClick={onClose}
                  >
                    <span
                      className="relative inline-flex shrink-0 mt-0.5"
                      data-testid={`remote-server-icon-${remote.id}`}
                    >
                      <Server className="h-3.5 w-3.5 text-base-content/70" aria-hidden="true" />
                      {isFailed && (
                        <span
                          data-testid={`remote-health-dot-${remote.id}`}
                          className="absolute -top-0.5 -right-0.5 h-1.5 w-1.5 rounded-full bg-error ring-1 ring-base-100"
                        />
                      )}
                    </span>
                    <div className="flex flex-col min-w-0 flex-1">
                      <span className="font-medium text-base-content truncate">{label}</span>
                      <span className="text-[11px] text-base-content/60 truncate max-w-[14rem]">
                        {url}
                      </span>
                    </div>
                  </a>
                </li>
              )
            })}
          </ul>
        )}
        {/* #933: every row here is a remote, so a path to manage them always
            belongs in this popup — not only in the empty state. */}
        <div className="mt-1 border-t border-base-300 pt-1 px-2">
          <button
            type="button"
            role="menuitem"
            className="flex w-full items-center gap-1.5 py-1.5 text-xs text-base-content/70 hover:text-base-content hover:bg-base-200 rounded"
            data-testid="manage-remotes-link"
            onClick={() => {
              onClose()
              onOpenSettingsRemotes()
            }}
          >
            <Settings2 className="h-3.5 w-3.5" aria-hidden="true" />
            Manage Remotes
          </button>
        </div>
      </div>
    </div>
  )
}
