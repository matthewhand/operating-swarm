/**
 * Issue #1256 — server filesystem directory picker modal.
 *
 * Browses host directories via GET /v1/fs/directories/ so a CLI agent's
 * Folder (process cwd) can be selected instead of typed. Confined to the
 * server's permitted roots; never shown for remote agents.
 */
import { useCallback, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { ChevronUp, Folder, GitBranch, Loader2 } from 'lucide-react'
import { Button, Modal } from './DaisyUI'
import { fetchDirectories, type FsDirectoryEntry } from '../lib/api'

export interface DirectoryPickerModalProps {
  open: boolean
  onClose: () => void
  onSelect: (path: string) => void
  /** Path to open the browser at; defaults to the server home directory. */
  initialPath?: string
}

function Segments({ path }: { path: string }) {
  const parts = path.split('/').filter(Boolean)
  return (
    <span className="truncate" data-testid="directory-picker-crumbs">
      {parts.length === 0 ? '/' : `/${parts.join(' / ')}`}
    </span>
  )
}

export default function DirectoryPickerModal({
  open,
  onClose,
  onSelect,
  initialPath = '',
}: DirectoryPickerModalProps) {
  const [listing, setListing] = useState<{ path: string; parent: string | null; entries: FsDirectoryEntry[] } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (path: string) => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchDirectories(path)
      setListing({ path: data.path, parent: data.parent, entries: data.entries })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not read that directory.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!open) {
      setListing(null)
      setError(null)
      return
    }
    void load(initialPath)
  }, [open, initialPath, load])

  const currentPath = listing?.path ?? ''

  // D4: this modal is mounted from inside AgentWorkspaceBinding, which lives
  // inside the Add-agent / Agent-editor `<form>`. A `<form class="modal-backdrop">`
  // descendant of a host form is invalid HTML (`validateDOMNesting`). Portal the
  // whole dialog to <body> so it always renders outside the host form.
  return createPortal(
    <Modal
      isOpen={open}
      onClose={onClose}
      title="Choose a folder"
      size="lg"
      aria-label="Choose a folder"
    >
      <div className="space-y-3" data-testid="directory-picker">
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => load(listing?.parent ?? '')}
            disabled={!listing?.parent}
            aria-label="Go up one directory"
            data-testid="directory-picker-up"
          >
            <ChevronUp className="h-4 w-4" aria-hidden="true" />
            Up
          </Button>
          <div
            className="flex-1 truncate rounded-lg border border-base-300 bg-base-200/50 px-3 py-1.5 font-mono text-xs"
            title={currentPath}
          >
            <Segments path={currentPath} />
          </div>
        </div>

        <div
          className="h-64 overflow-y-auto rounded-lg border border-base-300 bg-base-100"
          role="listbox"
          aria-label="Directories"
        >
          {loading ? (
            <div className="flex items-center gap-2 p-4 text-sm text-base-content/60" data-testid="directory-picker-loading">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Loading…
            </div>
          ) : error ? (
            <div className="p-4 text-sm text-error" data-testid="directory-picker-error">
              {error}
            </div>
          ) : listing && listing.entries.length === 0 ? (
            <div className="p-4 text-sm text-base-content/60" data-testid="directory-picker-empty">
              No subfolders here.
            </div>
          ) : (
            <ul className="menu w-full p-1">
              {(listing?.entries ?? []).map((entry) => (
                <li key={entry.path}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={false}
                    className="flex w-full items-center gap-2 font-mono text-xs"
                    onClick={() => load(entry.path)}
                    data-testid={`directory-entry-${entry.name}`}
                    data-git-repo={entry.is_git_repo ? 'true' : 'false'}
                  >
                    <Folder className="h-3.5 w-3.5 shrink-0 text-base-content/50" aria-hidden="true" />
                    <span className="truncate">{entry.name}</span>
                    {entry.is_git_repo ? (
                      <span
                        className="ml-auto inline-flex items-center gap-1 rounded-full bg-base-300 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-base-content/70"
                        data-testid={`directory-git-${entry.name}`}
                      >
                        <GitBranch className="h-3 w-3" aria-hidden="true" />
                        git
                      </span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex items-center justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="primary"
            size="sm"
            disabled={!currentPath || loading}
            onClick={() => {
              if (currentPath) onSelect(currentPath)
            }}
            data-testid="directory-picker-select"
          >
            Select this folder
          </Button>
        </div>
      </div>
    </Modal>,
    document.body,
  )
}
