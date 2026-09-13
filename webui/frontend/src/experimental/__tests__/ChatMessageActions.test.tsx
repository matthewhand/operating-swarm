import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ToastProvider } from '../../components/DaisyUI'
import { ChatMessageActions } from '../ChatMessageActions'

function renderActions(text: string, onRetry?: () => void) {
  return render(
    <ToastProvider>
      <ChatMessageActions text={text} onRetry={onRetry} />
    </ToastProvider>,
  )
}

describe('ChatMessageActions', () => {
  it('renders no Copy button — Copy lives only in MessageRowActions (#70)', () => {
    renderActions('hello **markdown**', vi.fn())
    expect(screen.queryByRole('button', { name: /copy/i })).not.toBeInTheDocument()
  })

  it('wires Retry and does not mount react/reply/more stubs', () => {
    const onRetry = vi.fn()
    renderActions('hi', onRetry)
    fireEvent.click(screen.getByRole('button', { name: 'Resend the previous message' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('button', { name: /react/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /reply/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /more/i })).not.toBeInTheDocument()
  })

  it('renders nothing when onRetry is not provided', () => {
    const { container } = renderActions('hi')
    expect(container.firstChild).toBeNull()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
