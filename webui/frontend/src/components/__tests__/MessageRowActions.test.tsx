import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ToastProvider } from '../DaisyUI'
import MessageRowActions from '../MessageRowActions'
import { COPY_EMPTY_TITLE, COPY_FAILED_TITLE } from '../../lib/clipboard'
import * as clipboard from '../../lib/clipboard'

function renderActions(text: string, children?: React.ReactNode) {
  return render(
    <ToastProvider>
      <div className="group/osrow">
        <MessageRowActions text={text}>{children}</MessageRowActions>
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
})
