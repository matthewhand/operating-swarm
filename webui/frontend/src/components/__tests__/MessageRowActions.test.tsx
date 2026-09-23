import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ToastProvider } from '../DaisyUI'
import MessageRowActions from '../MessageRowActions'
import { COPY_EMPTY_TITLE, COPY_FAILED_TITLE } from '../../lib/clipboard'
import * as clipboard from '../../lib/clipboard'
import type { ComponentProps } from 'react'

type ActionProps = Omit<ComponentProps<typeof MessageRowActions>, 'text' | 'children'>

function renderActions(text: string, children?: React.ReactNode, props: ActionProps = {}) {
  return render(
    <ToastProvider>
      <div className="group/osrow">
        <MessageRowActions text={text} {...props}>
          {children}
        </MessageRowActions>
      </div>
    </ToastProvider>,
  )
}

describe('MessageRowActions', () => {
  beforeEach(() => {
    vi.spyOn(clipboard, 'copyTextToClipboard').mockResolvedValue('copied')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('copies assistant markdown via the hover Copy control (#70 / REQ-103)', async () => {
    renderActions('hello **markdown**')
    const button = screen.getByRole('button', { name: 'Copy message' })
    expect(button).toBeInTheDocument()
    fireEvent.click(button)
    await waitFor(() => {
      expect(clipboard.copyTextToClipboard).toHaveBeenCalledWith('hello **markdown**')
    })
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument()
  })

  it('disables Copy when the row has no text (ChatPage also skips the mount)', () => {
    renderActions('   ')
    expect(screen.getByRole('button', { name: COPY_EMPTY_TITLE })).toBeDisabled()
    expect(clipboard.copyTextToClipboard).not.toHaveBeenCalled()
  })

  it('toasts when clipboard write fails', async () => {
    vi.mocked(clipboard.copyTextToClipboard).mockResolvedValue('failed')
    renderActions('still stuck')
    fireEvent.click(screen.getByRole('button', { name: 'Copy message' }))
    expect(await screen.findByText(COPY_FAILED_TITLE)).toBeInTheDocument()
  })

  it('renders horizontal container with testid and hover reveal classes', () => {
    renderActions('hello', <button type="button">Extra Action</button>)
    const container = screen.getByTestId('os-message-row-actions')
    expect(container).toBeInTheDocument()
    expect(container.className).toContain('flex')
    expect(container.className).toContain('flex-row')
    expect(container.className).toContain('items-center')
    expect(container.className).toContain('gap-1')
    expect(container.className).toContain('group-hover/osrow:md:opacity-100')
    expect(container.className).toContain('group-focus-within/osrow:md:opacity-100')
    expect(screen.getByRole('button', { name: 'Extra Action' })).toBeInTheDocument()
  })

  it('renders Edit before Copy when canEdit is true and starts edit on click (REQ-869)', () => {
    const onStartEdit = vi.fn()
    renderActions('hello', undefined, { canEdit: true, onStartEdit })
    const row = screen.getByTestId('os-message-row-actions')
    const buttons = within(row).getAllByRole('button')
    expect(buttons[0]).toHaveAttribute('aria-label', 'Edit message')
    expect(buttons[1]).toHaveAttribute('aria-label', 'Copy message')
    fireEvent.click(buttons[0])
    expect(onStartEdit).toHaveBeenCalledTimes(1)
  })

  it('does not render Edit when canEdit is false', () => {
    renderActions('hello')
    expect(screen.queryByRole('button', { name: 'Edit message' })).not.toBeInTheDocument()
  })

  it('shows Compress to here in the same row when canCompress is set (REQ-87)', () => {
    const onCompress = vi.fn()
    renderActions('older turn', undefined, { canCompress: true, onCompressToHere: onCompress })
    const row = screen.getByTestId('os-message-row-actions')
    const button = within(row).getByRole('button', { name: 'Compress to here' })
    fireEvent.click(button)
    expect(onCompress).toHaveBeenCalledTimes(1)
  })

  it('shows Start context from here when strategy is cull (REQ-121)', () => {
    const onStart = vi.fn()
    renderActions('later turn', undefined, {
      canCompress: true,
      contextStrategy: 'cull',
      onCompressToHere: onStart,
    })
    const button = screen.getByRole('button', { name: 'Start context from here' })
    expect(button).toHaveAttribute('title', 'Start context from here.')
    expect(screen.getByTestId('start-context-from-here')).toBeInTheDocument()
    fireEvent.click(button)
    expect(onStart).toHaveBeenCalledTimes(1)
  })

  it('renders Reply button when onReply is provided and triggers callback (#578)', () => {
    const onReply = vi.fn()
    renderActions('assistant reply text', undefined, { onReply })
    const replyButton = screen.getByTestId('message-reply-action')
    expect(replyButton).toBeInTheDocument()
    expect(replyButton).toHaveAttribute('aria-label', 'Reply to message')
    fireEvent.click(replyButton)
    expect(onReply).toHaveBeenCalledTimes(1)
  })

  it('does not render Reply button when onReply is omitted', () => {
    renderActions('plain message')
    expect(screen.queryByTestId('message-reply-action')).not.toBeInTheDocument()
  })
})

