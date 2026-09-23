import { AlertCircle, File, FileCode, FileSpreadsheet, FileText, Loader2, X } from 'lucide-react'
import {
  attachmentCategory,
  formatFileSize,
  isImageFile,
  type AttachmentCategory,
  type PendingAttachment,
} from '../lib/chatAttachments'

interface ComposerAttachChipsProps {
  attachments: PendingAttachment[]
  onRemove: (localId: string) => void
}

function AttachmentIcon({ category }: { category: AttachmentCategory }) {
  switch (category) {
    case 'table':
      return <FileSpreadsheet className="h-5 w-5 text-emerald-500 shrink-0" aria-hidden="true" />
    case 'code':
      return <FileCode className="h-5 w-5 text-blue-500 shrink-0" aria-hidden="true" />
    case 'document':
      return <FileText className="h-5 w-5 text-amber-500 shrink-0" aria-hidden="true" />
    default:
      return <File className="h-5 w-5 text-base-content/70 shrink-0" aria-hidden="true" />
  }
}

export default function ComposerAttachChips({
  attachments,
  onRemove,
}: ComposerAttachChipsProps) {
  if (attachments.length === 0) return null

  return (
    <ul className="os-attach-chips" aria-label="Attached files">
      {attachments.map((item) => {
        const isImage = isImageFile(item) && Boolean(item.previewUrl)
        const category = attachmentCategory(item)

        return (
          <li
            key={item.localId}
            data-testid="attachment-card"
            data-category={category}
            className={`os-attach-chip ${isImage ? 'os-attach-chip--image' : 'os-attach-chip--file'} group`}
          >
            <div className="os-attach-chip__content">
              {isImage ? (
                <img
                  className="os-attach-chip__thumb"
                  src={item.previewUrl || ''}
                  alt={item.name}
                  title={`${item.name} (${formatFileSize(item.size)})`}
                  data-testid="attachment-thumbnail"
                />
              ) : (
                <div className="os-attach-chip__file-info" title={`${item.name} (${formatFileSize(item.size)})`}>
                  <span className="os-attach-chip__icon" data-testid="attachment-icon">
                    <AttachmentIcon category={category} />
                  </span>
                  <div className="os-attach-chip__details">
                    <span className="os-attach-chip__name">{item.name}</span>
                    <span className="os-attach-chip__size">{formatFileSize(item.size)}</span>
                  </div>
                </div>
              )}

              {item.status === 'uploading' && (
                <div
                  className="os-attach-chip__overlay os-attach-chip__overlay--uploading"
                  data-testid="attachment-uploading"
                >
                  <Loader2 className="h-5 w-5 animate-spin text-primary shrink-0" aria-hidden="true" />
                  <span className="sr-only">Uploading {item.name}…</span>
                </div>
              )}

              {item.status === 'error' && (
                <div
                  className="os-attach-chip__overlay os-attach-chip__overlay--error"
                  data-testid="attachment-error"
                >
                  <AlertCircle className="h-4 w-4 text-error shrink-0" aria-hidden="true" />
                  <span className="os-attach-chip__error-label">Failed</span>
                  <span className="sr-only">Upload failed for {item.name}</span>
                </div>
              )}
            </div>

            <button
              type="button"
              className="os-attach-chip__remove"
              aria-label={`Remove ${item.name}`}
              data-testid={`attachment-remove-${item.localId}`}
              title={`Remove ${item.name}`}
              onClick={(e) => {
                e.stopPropagation()
                onRemove(item.localId)
              }}
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </li>
        )
      })}
    </ul>
  )
}
