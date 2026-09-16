/**
 * Composer file attachments (REQ-38).
 *
 * Upload is POST /v1/chat/attachments/ (multipart ``file``). The next chat
 * send includes the returned ids so the consumer can put the files in context.
 */

import { apiPostForm, ensureCsrfCookie } from './api'

export const CHAT_ATTACHMENTS_PATH = '/v1/chat/attachments/'

export interface ChatAttachmentRecord {
  id: string
  name: string
  size: number
  content_type: string
}

export interface PendingAttachment {
  localId: string
  file: File
  name: string
  size: number
  type: string
  previewUrl: string | null
  uploadId: string | null
  status: 'uploading' | 'ready' | 'error'
  error?: string
}

export function isImageFile(file: Pick<File, 'type'> | { type: string }): boolean {
  return (file.type || '').toLowerCase().startsWith('image/')
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function attachmentCaption(names: string[]): string {
  if (names.length === 0) return 'Attached file'
  if (names.length === 1) return `Attached ${names[0]}`
  return `Attached ${names.join(', ')}`
}

export function dataTransferHasFiles(types: ArrayLike<string> | null | undefined): boolean {
  if (!types) return false
  return Array.from(types).includes('Files')
}

export function filesFromList(list: FileList | File[] | null | undefined): File[] {
  if (!list) return []
  return Array.from(list).filter((file) => file instanceof File && file.size >= 0)
}

/** Image files from a Ctrl/Cmd+V clipboard DataTransfer (REQ-811). */
export function imageFilesFromClipboard(
  data: DataTransfer | { files?: FileList | File[] | null; items?: DataTransferItemList | ArrayLike<DataTransferItem> | null } | null | undefined,
): File[] {
  if (!data) return []
  const fromFiles = filesFromList(data.files).filter(isImageFile)
  if (fromFiles.length > 0) return fromFiles
  const items = data.items
  if (!items) return []
  const out: File[] = []
  for (const item of Array.from(items as ArrayLike<DataTransferItem>)) {
    if (!item || item.kind !== 'file') continue
    if (!isImageFile({ type: item.type || '' })) continue
    const file = item.getAsFile?.()
    if (file) out.push(file)
  }
  return out
}

let localIdCounter = 0

export function nextAttachmentLocalId(): string {
  localIdCounter += 1
  return `att-local-${localIdCounter}`
}

export function createPendingAttachment(file: File): PendingAttachment {
  const previewUrl = isImageFile(file) ? createPreviewUrl(file) : null
  return {
    localId: nextAttachmentLocalId(),
    file,
    name: file.name || 'file',
    size: file.size,
    type: file.type || '',
    previewUrl,
    uploadId: null,
    status: 'uploading',
  }
}

function createPreviewUrl(file: File): string | null {
  try {
    return URL.createObjectURL(file)
  } catch {
    return null
  }
}

export function revokePreviewUrl(url: string | null | undefined): void {
  if (!url) return
  try {
    URL.revokeObjectURL(url)
  } catch {
    // jsdom / already-revoked
  }
}

export async function uploadChatAttachment(file: File): Promise<ChatAttachmentRecord> {
  await ensureCsrfCookie()
  const body = new FormData()
  body.append('file', file, file.name || 'file')
  return apiPostForm<ChatAttachmentRecord>(CHAT_ATTACHMENTS_PATH, body)
}

export function readyAttachmentIds(items: PendingAttachment[]): string[] {
  return items
    .map((item) => item.uploadId)
    .filter((id): id is string => typeof id === 'string' && id.length > 0)
}
