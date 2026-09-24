import { act, useEffect } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  DEFAULT_TOAST_TTLS,
  NOTIFICATIONS_AUTO_EXPIRE_KEY,
  ToastProvider,
  TOAST_KIND_WS_DISCONNECT,
  useToast,
  saveNotificationsAutoExpire,
  resolveToastTtl,
} from '../Toast'

function ToastProbe() {
  const { addToast, dismissByKind, success, error, warning, info } = useToast()
  return (
    <div>
      <button
        type="button"
        onClick={() =>
          addToast({
            kind: TOAST_KIND_WS_DISCONNECT,
            type: 'error',
            title: 'Chat disconnected',
            message: 'The chat websocket closed.',
          })
        }
      >
        fire-disconnect
      </button>
      <button
        type="button"
        onClick={() =>
          addToast({
            kind: TOAST_KIND_WS_DISCONNECT,
            type: 'error',
            title: 'Chat websocket unreachable',
            message: 'ASGI is not serving /ws/.',
          })
        }
      >
        fire-unreachable
      </button>
      <button
        type="button"
        onClick={() =>
          addToast({
            type: 'info',
            title: 'Copied',
            message: 'Message copied.',
          })
        }
      >
        fire-copy
      </button>
      <button type="button" onClick={() => dismissByKind(TOAST_KIND_WS_DISCONNECT)}>
        dismiss-disconnect
      </button>

      {/* Classification triggers */}
      <button
        type="button"
        onClick={() =>
          addToast({
            type: 'success',
            title: 'Action completed',
            message: 'Saved successfully',
          })
        }
      >
        fire-success-action
      </button>
      <button
        type="button"
        onClick={() =>
          addToast({
            type: 'warning',
            title: 'Resource warning',
            message: 'Token limit approaching',
          })
        }
      >
        fire-warning
      </button>
      <button
        type="button"
        onClick={() =>
          addToast({
            type: 'error',
            title: 'Send failed',
            message: 'Failed to send turn',
          })
        }
      >
        fire-error
      </button>
      <button
        type="button"
        onClick={() =>
          addToast({
            type: 'info',
            category: 'action',
            title: 'Category action',
            message: 'Action via category',
          })
        }
      >
        fire-category-action
      </button>
      <button
        type="button"
        onClick={() =>
          addToast({
            type: 'info',
            category: 'sticky',
            title: 'Sticky category',
            message: 'Must stay visible',
          })
        }
      >
        fire-sticky-category
      </button>
      <button
        type="button"
        onClick={() =>
          addToast({
            type: 'error',
            sticky: true,
            title: 'Sticky error',
            message: 'Connection drop requires approval',
          })
        }
      >
        fire-sticky-flag
      </button>
      <button
        type="button"
        onClick={() =>
          addToast({
            type: 'info',
            duration: 0,
            title: 'Duration zero',
            message: 'Persistent prompt',
          })
        }
      >
        fire-zero-duration
      </button>
      <button
        type="button"
        onClick={() =>
          addToast({
            type: 'error',
            ttl: 2000,
            title: 'Custom TTL',
            message: 'Custom override',
          })
        }
      >
        fire-custom-ttl
      </button>
      <button
        type="button"
        onClick={() => success('Helper success', 'Saved via helper')}
      >
        fire-helper-success
      </button>
      <button
        type="button"
        onClick={() => info('Helper info', 'Info via helper')}
      >
        fire-helper-info
      </button>
      <button
        type="button"
        onClick={() => warning('Helper warning', 'Warning via helper')}
      >
        fire-helper-warning
      </button>
      <button
        type="button"
        onClick={() => error('Helper error', 'Error via helper')}
      >
        fire-helper-error
      </button>
    </div>
  )
}

function disconnectToasts() {
  return document.querySelectorAll(`[data-toast-kind="${TOAST_KIND_WS_DISCONNECT}"]`)
}

describe('Toast kind dedupe (REQ-112 #489)', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('keeps at most one disconnect toast and updates it instead of stacking', () => {
    render(
      <ToastProvider>
        <ToastProbe />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'fire-disconnect' }))
    fireEvent.click(screen.getByRole('button', { name: 'fire-disconnect' }))
    fireEvent.click(screen.getByRole('button', { name: 'fire-unreachable' }))

    expect(disconnectToasts()).toHaveLength(1)
    expect(screen.getByText('Chat websocket unreachable')).toBeInTheDocument()
    expect(screen.queryByText('Chat disconnected')).not.toBeInTheDocument()
  })

  it('dismisses only disconnect-kind toasts, leaving unrelated ones', () => {
    render(
      <ToastProvider>
        <ToastProbe />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'fire-disconnect' }))
    fireEvent.click(screen.getByRole('button', { name: 'fire-copy' }))
    expect(screen.getByText('Chat disconnected')).toBeInTheDocument()
    expect(screen.getByText('Copied')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'dismiss-disconnect' }))

    expect(disconnectToasts()).toHaveLength(0)
    expect(screen.queryByText('Chat disconnected')).not.toBeInTheDocument()
    expect(screen.getByText('Copied')).toBeInTheDocument()
    expect(screen.getByText('Message copied.')).toBeInTheDocument()
  })

  it('does not stack when a consumer remounts and fires the same kind again', () => {
    function FireOnMount() {
      const { addToast } = useToast()
      useEffect(() => {
        addToast({
          kind: TOAST_KIND_WS_DISCONNECT,
          type: 'error',
          title: 'Chat disconnected',
          message: 'The chat websocket closed.',
        })
      }, [addToast])
      return null
    }

    const { rerender } = render(
      <ToastProvider>
        <FireOnMount key="first" />
      </ToastProvider>,
    )
    expect(disconnectToasts()).toHaveLength(1)

    rerender(
      <ToastProvider>
        <FireOnMount key="second" />
      </ToastProvider>,
    )
    expect(disconnectToasts()).toHaveLength(1)
    expect(screen.getAllByText('Chat disconnected')).toHaveLength(1)
  })
})

describe('Toast auto-expiry & classification (#1123)', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    localStorage.clear()
  })

  it('resolves correct default TTLs by type and category', () => {
    expect(DEFAULT_TOAST_TTLS.success).toBe(4000)
    expect(DEFAULT_TOAST_TTLS.info).toBe(6000)
    expect(DEFAULT_TOAST_TTLS.warning).toBe(8000)
    expect(DEFAULT_TOAST_TTLS.error).toBe(12000)

    expect(resolveToastTtl({ type: 'success' })).toEqual({ isSticky: false, ttl: 4000 })
    expect(resolveToastTtl({ type: 'info' })).toEqual({ isSticky: false, ttl: 6000 })
    expect(resolveToastTtl({ type: 'warning' })).toEqual({ isSticky: false, ttl: 8000 })
    expect(resolveToastTtl({ type: 'error' })).toEqual({ isSticky: false, ttl: 12000 })

    // Category overrides
    expect(resolveToastTtl({ type: 'info', category: 'action' })).toEqual({ isSticky: false, ttl: 4000 })
    expect(resolveToastTtl({ type: 'info', category: 'sticky' })).toEqual({ isSticky: true, ttl: 0 })
    expect(resolveToastTtl({ type: 'error', sticky: true })).toEqual({ isSticky: true, ttl: 0 })
    expect(resolveToastTtl({ type: 'info', ttl: 0 })).toEqual({ isSticky: true, ttl: 0 })
    expect(resolveToastTtl({ type: 'info', duration: 0 })).toEqual({ isSticky: true, ttl: 0 })
    expect(resolveToastTtl({ type: 'error', ttl: 2500 })).toEqual({ isSticky: false, ttl: 2500 })
  })

  it('auto-expires action / success toasts after ~4000ms', () => {
    render(
      <ToastProvider>
        <ToastProbe />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'fire-success-action' }))
    expect(screen.getByText('Action completed')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(3999)
    })
    expect(screen.getByText('Action completed')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.queryByText('Action completed')).not.toBeInTheDocument()
  })

  it('auto-expires info toasts after ~6000ms', () => {
    render(
      <ToastProvider>
        <ToastProbe />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'fire-copy' }))
    expect(screen.getByText('Copied')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(5999)
    })
    expect(screen.getByText('Copied')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.queryByText('Copied')).not.toBeInTheDocument()
  })

  it('auto-expires warning toasts after ~8000ms', () => {
    render(
      <ToastProvider>
        <ToastProbe />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'fire-warning' }))
    expect(screen.getByText('Resource warning')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(7999)
    })
    expect(screen.getByText('Resource warning')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.queryByText('Resource warning')).not.toBeInTheDocument()
  })

  it('auto-expires error toasts after ~12000ms', () => {
    render(
      <ToastProvider>
        <ToastProbe />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'fire-error' }))
    expect(screen.getByText('Send failed')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(11999)
    })
    expect(screen.getByText('Send failed')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.queryByText('Send failed')).not.toBeInTheDocument()
  })

  it('supports category: "action" with 4000ms TTL', () => {
    render(
      <ToastProvider>
        <ToastProbe />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'fire-category-action' }))
    expect(screen.getByText('Category action')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(3999)
    })
    expect(screen.getByText('Category action')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.queryByText('Category action')).not.toBeInTheDocument()
  })

  it('respects custom TTL overrides', () => {
    render(
      <ToastProvider>
        <ToastProbe />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'fire-custom-ttl' }))
    expect(screen.getByText('Custom TTL')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(1999)
    })
    expect(screen.getByText('Custom TTL')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.queryByText('Custom TTL')).not.toBeInTheDocument()
  })

  it('keeps sticky toasts visible indefinitely until dismissed', () => {
    render(
      <ToastProvider>
        <ToastProbe />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'fire-sticky-flag' }))
    fireEvent.click(screen.getByRole('button', { name: 'fire-sticky-category' }))
    fireEvent.click(screen.getByRole('button', { name: 'fire-zero-duration' }))

    expect(screen.getByText('Sticky error')).toBeInTheDocument()
    expect(screen.getByText('Sticky category')).toBeInTheDocument()
    expect(screen.getByText('Duration zero')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(60000)
    })

    expect(screen.getByText('Sticky error')).toBeInTheDocument()
    expect(screen.getByText('Sticky category')).toBeInTheDocument()
    expect(screen.getByText('Duration zero')).toBeInTheDocument()

    // Dismiss manually
    const dismissButtons = screen.getAllByRole('button', { name: 'Dismiss notification' })
    expect(dismissButtons.length).toBe(3)
    fireEvent.click(dismissButtons[0])

    expect(screen.queryByText('Sticky error')).not.toBeInTheDocument()
    expect(screen.getByText('Sticky category')).toBeInTheDocument()
  })

  it('pauses expiry timer on hover and resumes on mouse leave', () => {
    render(
      <ToastProvider>
        <ToastProbe />
      </ToastProvider>,
    )

    // Success toast has 4000ms TTL
    fireEvent.click(screen.getByRole('button', { name: 'fire-success-action' }))
    const toast = screen.getByRole('status')
    expect(toast).toHaveTextContent('Action completed')

    // Advance 1500ms (2500ms remaining)
    act(() => {
      vi.advanceTimersByTime(1500)
    })
    expect(toast).toBeInTheDocument()

    // Hover over toast -> timer should pause
    fireEvent.mouseEnter(toast)

    // Advance 10,000ms while hovering -> toast must NOT expire
    act(() => {
      vi.advanceTimersByTime(10000)
    })
    expect(toast).toBeInTheDocument()

    // Mouse leave -> timer should resume with remaining 2500ms
    fireEvent.mouseLeave(toast)

    // Advance 2400ms -> still in document (100ms remaining)
    act(() => {
      vi.advanceTimersByTime(2400)
    })
    expect(toast).toBeInTheDocument()

    // Advance 100ms -> expired and removed
    act(() => {
      vi.advanceTimersByTime(100)
    })
    expect(screen.queryByText('Action completed')).not.toBeInTheDocument()
  })

  it('honors user setting swarm_notifications_auto_expire disabled in localStorage', () => {
    localStorage.setItem(NOTIFICATIONS_AUTO_EXPIRE_KEY, 'false')

    render(
      <ToastProvider>
        <ToastProbe />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'fire-success-action' }))
    expect(screen.getByText('Action completed')).toBeInTheDocument()

    // Since auto-expire is disabled, even after 60 seconds it remains sticky
    act(() => {
      vi.advanceTimersByTime(60000)
    })
    expect(screen.getByText('Action completed')).toBeInTheDocument()
  })

  it('reacts dynamically when auto-expire preference is toggled via saveNotificationsAutoExpire', () => {
    render(
      <ToastProvider>
        <ToastProbe />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'fire-success-action' }))
    expect(screen.getByText('Action completed')).toBeInTheDocument()

    // Disable auto-expiry dynamically
    act(() => {
      saveNotificationsAutoExpire(false)
    })

    // Advance 10,000ms -> toast stays sticky
    act(() => {
      vi.advanceTimersByTime(10000)
    })
    expect(screen.getByText('Action completed')).toBeInTheDocument()

    // Re-enable auto-expiry dynamically
    act(() => {
      saveNotificationsAutoExpire(true)
    })

    // Should expire within 4000ms
    act(() => {
      vi.advanceTimersByTime(4000)
    })
    expect(screen.queryByText('Action completed')).not.toBeInTheDocument()
  })

  it('applies default TTLs to helper methods (success, info, warning, error)', () => {
    render(
      <ToastProvider>
        <ToastProbe />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'fire-helper-success' }))
    expect(screen.getByText('Helper success')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(3999)
    })
    expect(screen.getByText('Helper success')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.queryByText('Helper success')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'fire-helper-info' }))
    expect(screen.getByText('Helper info')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(5999)
    })
    expect(screen.getByText('Helper info')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.queryByText('Helper info')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'fire-helper-warning' }))
    expect(screen.getByText('Helper warning')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(7999)
    })
    expect(screen.getByText('Helper warning')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.queryByText('Helper warning')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'fire-helper-error' }))
    expect(screen.getByText('Helper error')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(11999)
    })
    expect(screen.getByText('Helper error')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.queryByText('Helper error')).not.toBeInTheDocument()
  })
})
