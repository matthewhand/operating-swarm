import { Button, Modal } from './DaisyUI'
import {
  KIND_LABELS,
  SKIP_REASON_LABELS,
  previewMemoryExport,
  type AgentMemory,
  type MemoryExportSkipReason,
} from '../lib/agentMemory'

export interface MemoryExportWizardProps {
  isOpen: boolean
  onClose: () => void
  agentId: string
  memories: AgentMemory[]
}

function reasonCount(
  excluded: Array<{ reason: MemoryExportSkipReason }>,
  reason: MemoryExportSkipReason,
): number {
  return excluded.filter((row) => row.reason === reason).length
}

export default function MemoryExportWizard({
  isOpen,
  onClose,
  agentId,
  memories,
}: MemoryExportWizardProps) {
  const preview = previewMemoryExport(memories)
  const episodeSkipped = reasonCount(preview.excluded, 'episode_skipped')
  const noteSkipped = reasonCount(preview.excluded, 'note_skipped')

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Template export preview"
      size="wizard"
      aria-label="Template export preview"
    >
      <div className="flex h-full min-h-0 flex-col gap-4" data-testid="memory-export-wizard">
        <p className="text-sm text-base-content/70">
          Pack split for{' '}
          <span className="font-medium text-base-content">{agentId || 'this agent'}</span>.
          Profile and log conventions are counted as included. Episodes and notes stay on this
          host. Pack export still strips emails, phone numbers, and private links; this preview
          does not apply that scrub.
        </p>

        <div className="grid grid-cols-2 gap-3" data-testid="memory-export-counts">
          <div className="rounded-box border border-base-300 bg-base-200/40 p-3">
            <p className="text-xs uppercase tracking-wide text-base-content/60">Included</p>
            <p className="text-2xl font-semibold" data-testid="memory-export-included-count">
              {preview.includedCount}
            </p>
            <p className="text-xs text-base-content/60">Pack-tier conventions</p>
          </div>
          <div className="rounded-box border border-base-300 bg-base-200/40 p-3">
            <p className="text-xs uppercase tracking-wide text-base-content/60">Excluded</p>
            <p className="text-2xl font-semibold" data-testid="memory-export-excluded-count">
              {preview.excludedCount}
            </p>
            <p className="text-xs text-base-content/60">Local memories skipped</p>
          </div>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
          <section data-testid="memory-export-included">
            <h3 className="text-sm font-semibold">Included in pack</h3>
            {preview.included.length === 0 ? (
              <p className="mt-1 text-sm text-base-content/60">No conventions to pack.</p>
            ) : (
              <ul className="mt-2 space-y-2">
                {preview.included.map((memory) => (
                  <li
                    key={memory.id}
                    className="rounded-box border border-base-300 bg-base-100 px-3 py-2"
                    data-testid={`memory-export-included-${memory.id}`}
                  >
                    <p className="text-sm font-medium">
                      {memory.title || KIND_LABELS[memory.kind]}
                    </p>
                    <p className="text-xs text-base-content/60">{KIND_LABELS[memory.kind]}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section data-testid="memory-export-excluded">
            <h3 className="text-sm font-semibold">Excluded from pack</h3>
            <ul className="mt-2 space-y-1 text-sm" data-testid="memory-export-reasons">
              {episodeSkipped > 0 ? (
                <li data-testid="memory-export-reason-episode">
                  {episodeSkipped} {SKIP_REASON_LABELS.episode_skipped}
                </li>
              ) : null}
              {noteSkipped > 0 ? (
                <li data-testid="memory-export-reason-note">
                  {noteSkipped} {SKIP_REASON_LABELS.note_skipped}
                </li>
              ) : null}
              {preview.excluded.length === 0 ? (
                <li className="text-base-content/60">Nothing local to skip.</li>
              ) : null}
            </ul>
          </section>
        </div>

        <div className="flex justify-end">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </Modal>
  )
}
