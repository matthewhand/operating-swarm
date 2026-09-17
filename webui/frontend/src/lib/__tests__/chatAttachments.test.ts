import { describe, it, expect } from 'vitest'
import {
  attachmentCaption,
  composerFileAttachSupported,
  createPendingAttachment,
  dataTransferHasFiles,
  filesFromList,
  formatFileSize,
  imageFilesFromClipboard,
  isImageFile,
  readyAttachmentIds,
} from '../chatAttachments'

describe('chatAttachments helpers', () => {
  it('#427 file attach is for API/blueprint, not CLI or remote', () => {
    expect(composerFileAttachSupported({})).toBe(true)
    expect(composerFileAttachSupported({ isCli: true })).toBe(false)
    expect(composerFileAttachSupported({ isRemote: true })).toBe(false)
  })

  it('classifies images and formats size', () => {
    expect(isImageFile({ type: 'image/png' })).toBe(true)
    expect(isImageFile({ type: 'text/plain' })).toBe(false)
    expect(formatFileSize(12)).toBe('12 B')
    expect(formatFileSize(2048)).toBe('2.0 KB')
  })

  it('reads files from a list and detects a Files drag', () => {
    const file = new File(['hello'], 'notes.txt', { type: 'text/plain' })
    expect(filesFromList([file])).toHaveLength(1)
    expect(dataTransferHasFiles(['Files'])).toBe(true)
    expect(dataTransferHasFiles(['text/plain'])).toBe(false)
  })

  it('pulls image files off a clipboard DataTransfer (REQ-811)', () => {
    const png = new File([new Uint8Array([1, 2, 3])], 'red.png', { type: 'image/png' })
    const notes = new File(['hello'], 'notes.txt', { type: 'text/plain' })
    expect(
      imageFilesFromClipboard({
        files: [png, notes],
        items: [],
        types: ['Files'],
      }).map((file) => file.name),
    ).toEqual(['red.png'])
    expect(
      imageFilesFromClipboard({
        files: [],
        items: [
          {
            kind: 'file',
            type: 'image/png',
            getAsFile: () => png,
          } as DataTransferItem,
        ],
      }),
    ).toEqual([png])
    expect(imageFilesFromClipboard({ files: [notes], items: [] })).toEqual([])
  })

  it('creates a pending chip and collects ready ids', () => {
    const file = new File(['hello'], 'notes.txt', { type: 'text/plain' })
    const pending = createPendingAttachment(file)
    expect(pending.name).toBe('notes.txt')
    expect(pending.status).toBe('uploading')
    expect(pending.previewUrl).toBeNull()
    expect(readyAttachmentIds([{ ...pending, uploadId: 'att-1' }])).toEqual(['att-1'])
    expect(attachmentCaption(['notes.txt'])).toBe('Attached notes.txt')
  })
})
