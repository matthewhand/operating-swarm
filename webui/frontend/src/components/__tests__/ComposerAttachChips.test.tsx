import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ComposerAttachChips from '../ComposerAttachChips'
import type { PendingAttachment } from '../../lib/chatAttachments'

describe('ComposerAttachChips (#835)', () => {
  it('renders nothing when attachments list is empty', () => {
    const onRemove = vi.fn()
    const { container } = render(<ComposerAttachChips attachments={[]} onRemove={onRemove} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders rich 64x64 preview thumbnails for image attachments', () => {
    const onRemove = vi.fn()
    const attachments: PendingAttachment[] = [
      {
        localId: 'att-1',
        file: new File(['data'], 'screenshot.png', { type: 'image/png' }),
        name: 'screenshot.png',
        size: 2048,
        type: 'image/png',
        previewUrl: 'blob:http://localhost/att-1',
        uploadId: 'upload-1',
        status: 'ready',
      },
    ]

    render(<ComposerAttachChips attachments={attachments} onRemove={onRemove} />)

    const card = screen.getByTestId('attachment-card')
    expect(card).toHaveClass('os-attach-chip--image')
    expect(card).toHaveAttribute('data-category', 'image')

    const thumb = screen.getByTestId('attachment-thumbnail')
    expect(thumb).toHaveAttribute('src', 'blob:http://localhost/att-1')
    expect(thumb).toHaveAttribute('alt', 'screenshot.png')
    expect(thumb).toHaveAttribute('title', 'screenshot.png (2.0 KB)')
  })

  it('renders category icons and formatted metadata for non-image files', () => {
    const onRemove = vi.fn()
    const attachments: PendingAttachment[] = [
      {
        localId: 'att-2',
        file: new File(['name,age\nAlice,30'], 'users.csv', { type: 'text/csv' }),
        name: 'users.csv',
        size: 512,
        type: 'text/csv',
        previewUrl: null,
        uploadId: 'upload-2',
        status: 'ready',
      },
      {
        localId: 'att-3',
        file: new File(['console.log(1)'], 'script.ts', { type: 'text/typescript' }),
        name: 'script.ts',
        size: 1024,
        type: 'text/typescript',
        previewUrl: null,
        uploadId: 'upload-3',
        status: 'ready',
      },
      {
        localId: 'att-4',
        file: new File(['report contents'], 'annual_report.pdf', { type: 'application/pdf' }),
        name: 'annual_report.pdf',
        size: 1048576,
        type: 'application/pdf',
        previewUrl: null,
        uploadId: 'upload-4',
        status: 'ready',
      },
    ]

    render(<ComposerAttachChips attachments={attachments} onRemove={onRemove} />)

    const cards = screen.getAllByTestId('attachment-card')
    expect(cards).toHaveLength(3)

    expect(cards[0]).toHaveClass('os-attach-chip--file')
    expect(cards[0]).toHaveAttribute('data-category', 'table')
    expect(cards[0]).toHaveTextContent('users.csv')
    expect(cards[0]).toHaveTextContent('512 B')

    expect(cards[1]).toHaveAttribute('data-category', 'code')
    expect(cards[1]).toHaveTextContent('script.ts')
    expect(cards[1]).toHaveTextContent('1.0 KB')

    expect(cards[2]).toHaveAttribute('data-category', 'document')
    expect(cards[2]).toHaveTextContent('annual_report.pdf')
    expect(cards[2]).toHaveTextContent('1.0 MB')
  })

  it('displays loading spinner overlay during upload', () => {
    const onRemove = vi.fn()
    const attachments: PendingAttachment[] = [
      {
        localId: 'att-uploading',
        file: new File(['data'], 'photo.jpg', { type: 'image/jpeg' }),
        name: 'photo.jpg',
        size: 4096,
        type: 'image/jpeg',
        previewUrl: 'blob:http://localhost/att-uploading',
        uploadId: null,
        status: 'uploading',
      },
    ]

    render(<ComposerAttachChips attachments={attachments} onRemove={onRemove} />)

    expect(screen.getByTestId('attachment-uploading')).toBeInTheDocument()
    expect(screen.getByText(/Uploading photo\.jpg/i)).toBeInTheDocument()
  })

  it('displays error overlay when upload fails', () => {
    const onRemove = vi.fn()
    const attachments: PendingAttachment[] = [
      {
        localId: 'att-failed',
        file: new File(['data'], 'broken.pdf', { type: 'application/pdf' }),
        name: 'broken.pdf',
        size: 1024,
        type: 'application/pdf',
        previewUrl: null,
        uploadId: null,
        status: 'error',
        error: 'Upload rejected',
      },
    ]

    render(<ComposerAttachChips attachments={attachments} onRemove={onRemove} />)

    expect(screen.getByTestId('attachment-error')).toBeInTheDocument()
    expect(screen.getByText('Failed')).toBeInTheDocument()
    expect(screen.getByText(/Upload failed for broken\.pdf/i)).toBeInTheDocument()
  })

  it('triggers onRemove when clicking the prominent dismissal button', () => {
    const onRemove = vi.fn()
    const attachments: PendingAttachment[] = [
      {
        localId: 'att-dismiss',
        file: new File(['data'], 'dismiss-me.png', { type: 'image/png' }),
        name: 'dismiss-me.png',
        size: 2048,
        type: 'image/png',
        previewUrl: 'blob:http://localhost/att-dismiss',
        uploadId: 'upload-dismiss',
        status: 'ready',
      },
    ]

    render(<ComposerAttachChips attachments={attachments} onRemove={onRemove} />)

    const removeBtn = screen.getByTestId('attachment-remove-att-dismiss')
    expect(removeBtn).toHaveAttribute('aria-label', 'Remove dismiss-me.png')

    fireEvent.click(removeBtn)
    expect(onRemove).toHaveBeenCalledTimes(1)
    expect(onRemove).toHaveBeenCalledWith('att-dismiss')
  })
})
