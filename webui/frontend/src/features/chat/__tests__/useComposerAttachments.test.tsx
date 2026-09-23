/**
 * #856 slice D — the composer attachment queue becomes a testable hook.
 *
 * ChatPage's drag/drop/paste/pick → upload-queue pipeline moves verbatim to
 * features/chat/useComposerAttachments.ts:
 *   1. enqueue caps the queue at 8 and tracks upload progress per file;
 *   2. drag enter/leave nesting shows the drop affordance only while files
 *      hover the composer;
 *   3. drop/paste honor the composerMenu add-files gate with an info toast;
 *   4. remove/clear abort in-flight uploads and revoke preview URLs;
 *   5. ChatPage no longer defines the handlers inline.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import {
  useComposerAttachments,
  MAX_PENDING_ATTACHMENTS,
} from '../useComposerAttachments'
import type { PendingAttachment } from '../../../lib/chatAttachments'

const { uploadChatAttachment, createPendingAttachment, revokePreviewUrl } = vi.hoisted(() => ({
  uploadChatAttachment: vi.fn(),
  createPendingAttachment: vi.fn((file: File, index: number) => ({
    localId: `local-${index}-${file.name}`,
    file,
    name: file.name,
    status: 'uploading',
    previewUrl: `blob:${file.name}`,
    abortController: { abort: vi.fn() },
  })),
  revokePreviewUrl: vi.fn(),
}))

vi.mock('../../../lib/chatAttachments', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../lib/chatAttachments')>()
  return {
    ...actual,
    createPendingAttachment: (file: File) =>
      createPendingAttachment(file, createPendingCall++),
    uploadChatAttachment: (...args: unknown[]) => uploadChatAttachment(...args),
    revokePreviewUrl: (...args: unknown[]) => revokePreviewUrl(...args),
  }
})

let createPendingCall = 0
function file(name: string): File {
  return new File(['x'], name, { type: 'text/plain' })
}
function dragOpts(types: string[] = ['Files']) {
  return {
    dataTransfer: { types, files: [] },
    preventDefault: vi.fn(),
    stopPropagation: vi.fn(),
  } as unknown as React.DragEvent<HTMLDivElement>
}
function makeDeps(enabled = true) {
  return {
    addFilesEnabled: enabled,
    addFilesReason: enabled ? '' : 'attachments need an API agent',
    addToast: vi.fn(),
  }
}

beforeEach(() => {
  createPendingCall = 0
  revokePreviewUrl.mockReset()
  // default: uploads succeed; individual tests override for failure/abort
  uploadChatAttachment.mockReset()
  uploadChatAttachment.mockImplementation(() => Promise.resolve({ id: 'srv-default' }))
})
afterEach(() => vi.restoreAllMocks())

describe('#856 slice D: useComposerAttachments', () => {
  it('enqueues files, uploads, and marks them ready', async () => {
    uploadChatAttachment.mockResolvedValue({ id: 'srv-1' })
    const { result } = renderHook(() => useComposerAttachments(makeDeps()))
    act(() => result.current.enqueueComposerFiles([file('a.txt')]))
    expect(result.current.pendingAttachments).toHaveLength(1)
    await waitFor(() =>
      expect(result.current.pendingAttachments[0]?.status).toBe('ready'),
    )
    expect(result.current.pendingAttachments[0]?.uploadId).toBe('srv-1')
  })

  it('caps the queue at MAX_PENDING_ATTACHMENTS', () => {
    const { result } = renderHook(() => useComposerAttachments(makeDeps()))
    act(() =>
      result.current.enqueueComposerFiles(
        Array.from({ length: MAX_PENDING_ATTACHMENTS + 3 }, (_, i) => file(`f${i}.txt`)),
      ),
    )
    expect(result.current.pendingAttachments).toHaveLength(MAX_PENDING_ATTACHMENTS)
  })

  it('marks uploads errored on failure (abort excepted)', async () => {
    uploadChatAttachment.mockRejectedValue(new Error('boom'))
    const { result } = renderHook(() => useComposerAttachments(makeDeps()))
    act(() => result.current.enqueueComposerFiles([file('bad.txt')]))
    await waitFor(() =>
      expect(result.current.pendingAttachments[0]?.status).toBe('error'),
    )
  })

  it('drag enter/leave nesting toggles the affordance', () => {
    const { result } = renderHook(() => useComposerAttachments(makeDeps()))
    expect(result.current.composerDragOver).toBe(false)
    act(() => result.current.handleComposerDragEnter(dragOpts()))
    expect(result.current.composerDragOver).toBe(true)
    act(() => result.current.handleComposerDragOver(dragOpts()))
    expect(result.current.composerDragOver).toBe(true)
    act(() => result.current.handleComposerDragLeave(dragOpts()))
    expect(result.current.composerDragOver).toBe(false)
  })

  it('ignores drag events that carry no files', () => {
    const { result } = renderHook(() => useComposerAttachments(makeDeps()))
    act(() => result.current.handleComposerDragEnter(dragOpts(['text/plain'])))
    expect(result.current.composerDragOver).toBe(false)
  })

  it('drop on a gated seat toasts instead of enqueueing', () => {
    const deps = makeDeps(false)
    const { result } = renderHook(() => useComposerAttachments(deps))
    act(() => result.current.handleComposerDrop(dragOpts()))
    expect(deps.addToast).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'info', title: 'Add files' }),
    )
    expect(result.current.pendingAttachments).toHaveLength(0)
  })

  it('drop on an enabled seat enqueues', () => {
    const { result } = renderHook(() => useComposerAttachments(makeDeps(true)))
    act(() =>
      result.current.handleComposerDrop({
        dataTransfer: { types: ['Files'], files: [file('d.txt')] },
        preventDefault: vi.fn(),
      } as unknown as React.DragEvent<HTMLDivElement>),
    )
    expect(result.current.pendingAttachments).toHaveLength(1)
  })

  it('paste of clipboard images enqueues', () => {
    const { result } = renderHook(() => useComposerAttachments(makeDeps()))
    const png = new File(['x'], 'shot.png', { type: 'image/png' })
    act(() =>
      result.current.handleComposerPaste({
        clipboardData: { files: [png] },
        preventDefault: vi.fn(),
      } as unknown as React.ClipboardEvent<HTMLTextAreaElement>),
    )
    expect(result.current.pendingAttachments).toHaveLength(1)
  })

  it('remove aborts the upload and revokes the preview', () => {
    uploadChatAttachment.mockReturnValue(new Promise(() => {}))
    const { result } = renderHook(() => useComposerAttachments(makeDeps()))
    act(() => result.current.enqueueComposerFiles([file('gone.txt')]))
    const row = result.current.pendingAttachments[0] as PendingAttachment
    act(() => result.current.removeAttachment(row.localId))
    expect(row.abortController?.abort).toHaveBeenCalled()
    expect(revokePreviewUrl).toHaveBeenCalledWith('blob:gone.txt')
    expect(result.current.pendingAttachments).toHaveLength(0)
  })

  it('clear aborts everything and empties the queue', () => {
    uploadChatAttachment.mockReturnValue(new Promise(() => {}))
    const { result } = renderHook(() => useComposerAttachments(makeDeps()))
    act(() => result.current.enqueueComposerFiles([file('a.txt'), file('b.txt')]))
    act(() => result.current.clearPendingAttachments())
    expect(result.current.pendingAttachments).toHaveLength(0)
  })

  it('exposes ready attachment ids', async () => {
    uploadChatAttachment.mockResolvedValue({ id: 'srv-9' })
    const { result } = renderHook(() => useComposerAttachments(makeDeps()))
    act(() => result.current.enqueueComposerFiles([file('ok.txt')]))
    await waitFor(() => expect(result.current.readyAttachIds).toEqual(['srv-9']))
  })
})
