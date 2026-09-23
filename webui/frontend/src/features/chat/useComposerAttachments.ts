/**
 * #856 slice D — the composer attachment queue, moved verbatim from
 * ChatPage.tsx: drag/drop/paste/pick → upload pipeline with per-file
 * progress, the 8-slot cap, the add-files capability gate, and the
 * abort/revoke cleanup contract.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import type { DragEvent, ClipboardEvent } from 'react'
import {
  createPendingAttachment,
  dataTransferHasFiles,
  filesFromList,
  imageFilesFromClipboard,
  readyAttachmentIds,
  revokePreviewUrl,
  uploadChatAttachment,
  type PendingAttachment,
} from '../../lib/chatAttachments'

/** The composer's attachment cap (was inline in ChatPage). */
export const MAX_PENDING_ATTACHMENTS = 8

export interface UseComposerAttachmentsDeps {
  /** composerMenu.addFiles.enabled — capability gate for attaching. */
  addFilesEnabled: boolean
  /** composerMenu.addFiles.reason — why attaching is unavailable. */
  addFilesReason: string
  /** Info toast sink for gated attempts. */
  addToast: (toast: { type: 'info'; title: string; message: string }) => void
}

export function useComposerAttachments(deps: UseComposerAttachmentsDeps) {
  const { addFilesEnabled, addFilesReason, addToast } = deps
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([])
  const [composerDragOver, setComposerDragOver] = useState(false)
  const dragCounterRef = useRef(0)

  const handleComposerDragEnter = useCallback((event: DragEvent<HTMLDivElement>) => {
    if (!dataTransferHasFiles(event.dataTransfer?.types)) return
    event.preventDefault()
    dragCounterRef.current += 1
    if (dragCounterRef.current === 1) {
      setComposerDragOver(true)
    }
  }, [])

  const handleComposerDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    if (!dataTransferHasFiles(event.dataTransfer?.types)) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
  }, [])

  const handleComposerDragLeave = useCallback((event: DragEvent<HTMLDivElement>) => {
    if (!dataTransferHasFiles(event.dataTransfer?.types)) return
    event.preventDefault()
    dragCounterRef.current = Math.max(0, dragCounterRef.current - 1)
    if (dragCounterRef.current === 0) {
      setComposerDragOver(false)
    }
  }, [])

  const enqueueComposerFiles = useCallback(
    (files: File[]) => {
      if (files.length === 0) return
      const room = Math.max(0, MAX_PENDING_ATTACHMENTS - pendingAttachments.length)
      const incoming = files.slice(0, room).map(createPendingAttachment)
      if (incoming.length === 0) return
      setPendingAttachments((prev) => [...prev, ...incoming])
      incoming.forEach((item) => {
        void uploadChatAttachment(item.file, item.abortController?.signal)
          .then((record) => {
            setPendingAttachments((prev) =>
              prev.map((row) =>
                row.localId === item.localId
                  ? { ...row, uploadId: record.id, status: 'ready' }
                  : row,
              ),
            )
          })
          .catch((err: unknown) => {
            if (
              (err instanceof DOMException && err.name === 'AbortError') ||
              (err as { name?: string })?.name === 'AbortError'
            ) {
              return
            }
            setPendingAttachments((prev) =>
              prev.map((row) =>
                row.localId === item.localId ? { ...row, status: 'error' } : row,
              ),
            )
          })
      })
    },
    [pendingAttachments.length],
  )

  const handleComposerDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      if (!dataTransferHasFiles(event.dataTransfer?.types)) return
      event.preventDefault()
      dragCounterRef.current = 0
      setComposerDragOver(false)
      if (!addFilesEnabled) {
        addToast({
          type: 'info',
          title: 'Add files',
          message: `${addFilesReason}. Switch to an API agent to attach.`,
        })
        return
      }
      const files = filesFromList(event.dataTransfer?.files)
      if (files.length > 0) {
        enqueueComposerFiles(files)
      }
    },
    [addToast, addFilesEnabled, addFilesReason, enqueueComposerFiles],
  )

  const handleComposerPaste = useCallback(
    (event: ClipboardEvent<HTMLTextAreaElement>) => {
      const files = imageFilesFromClipboard(event.clipboardData)
      if (files.length === 0) return
      event.preventDefault()
      if (!addFilesEnabled) {
        addToast({
          type: 'info',
          title: 'Add files',
          message: `${addFilesReason}. Switch to an API agent to attach.`,
        })
        return
      }
      enqueueComposerFiles(files)
    },
    [addToast, addFilesEnabled, addFilesReason, enqueueComposerFiles],
  )

  const removeAttachment = useCallback((localId: string) => {
    setPendingAttachments((prev) => {
      const gone = prev.find((row) => row.localId === localId)
      gone?.abortController?.abort()
      revokePreviewUrl(gone?.previewUrl)
      return prev.filter((row) => row.localId !== localId)
    })
  }, [])

  const clearPendingAttachments = useCallback(() => {
    setPendingAttachments((prev) => {
      prev.forEach((item) => {
        item.abortController?.abort()
        revokePreviewUrl(item.previewUrl)
      })
      return []
    })
  }, [])

  const pendingAttachmentsRef = useRef(pendingAttachments)
  useEffect(() => {
    pendingAttachmentsRef.current = pendingAttachments
  }, [pendingAttachments])

  useEffect(() => {
    return () => {
      pendingAttachmentsRef.current.forEach((item) => {
        item.abortController?.abort()
        revokePreviewUrl(item.previewUrl)
      })
    }
  }, [])

  return {
    pendingAttachments,
    setPendingAttachments,
    composerDragOver,
    readyAttachIds: readyAttachmentIds(pendingAttachments),
    enqueueComposerFiles,
    handleComposerDragEnter,
    handleComposerDragOver,
    handleComposerDragLeave,
    handleComposerDrop,
    handleComposerPaste,
    removeAttachment,
    clearPendingAttachments,
  }
}
