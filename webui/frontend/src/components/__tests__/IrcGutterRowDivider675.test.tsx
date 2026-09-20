/**
 * #675 — the per-row IRC gutter divider.
 *
 * Rendered as the first child of every `.chat` row, right after the `::before`
 * gutter, so the transcript's rows share one straight vertical edge. The drag
 * persists the width through the shared store (save fires the change event;
 * the transcript root re-syncs its CSS var), double-click resets.
 */
import { describe, expect, it, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ChatMessageBubble } from '../ChatMessageBubble'
import { ToastProvider } from '../DaisyUI'
import {
  IRC_GUTTER_DEFAULT_PX,
  IRC_GUTTER_MAX_PX,
  IRC_GUTTER_MIN_PX,
  IRC_GUTTER_STORAGE_KEY,
  loadIrcGutterPx,
  saveIrcGutterPx,
} from '../../lib/ircGutter'
import type { BubbleTheme } from '../../lib/bubbleTheme'

beforeEach(() => {
  localStorage.clear()
})

function renderRow(theme: BubbleTheme) {
  return render(
    <ToastProvider>
      <ChatMessageBubble
        theme={theme}
        role="assistant"
        agentName="Ada"
        text="hello"
        ts="2026-09-20T10:00:00Z"
        streaming={false}
        editing={false}
        onCancelEdit={() => {}}
        onSaveEdit={() => {}}
      />
    </ToastProvider>,
  )
}

describe('#675 per-row IRC gutter divider', () => {
  it('renders a separator between gutter and body in IRC rows only', () => {
    const view = renderRow('irc')
    const row = document.querySelector('.chat') as HTMLElement // eslint-disable-line testing-library/no-node-access
    expect(row).not.toBeNull()
    const div = screen.getByTestId('irc-gutter-divider') as HTMLElement
    expect(div.getAttribute('role')).toBe('separator')
    // eslint-disable-next-line testing-library/no-node-access
    expect(row.firstElementChild).toBe(div)

    view.rerender(
      <ToastProvider>
        <ChatMessageBubble
          theme="simple"
          role="assistant"
          agentName="Ada"
          text="hello"
          ts="2026-09-20T10:00:00Z"
          streaming={false}
          editing={false}
          onCancelEdit={() => {}}
          onSaveEdit={() => {}}
        />
      </ToastProvider>,
    )
    expect(screen.queryByTestId('irc-gutter-divider')).toBeNull()
    view.unmount()
  })

  it('drag persists the clamped width', () => {
    saveIrcGutterPx(140)
    const view = renderRow('irc')
    const div = screen.getByTestId('irc-gutter-divider')
    fireEvent.pointerDown(div, { pointerId: 1, clientX: 100 })
    fireEvent.pointerMove(div, { pointerId: 1, clientX: 160 })
    fireEvent.pointerUp(div, { pointerId: 1, clientX: 160 })
    expect(loadIrcGutterPx()).toBe(200)
    view.unmount()
  })

  it('clamps to the configured bounds', () => {
    saveIrcGutterPx(140)
    const view = renderRow('irc')
    const div = screen.getByTestId('irc-gutter-divider')
    fireEvent.pointerDown(div, { pointerId: 1, clientX: 100 })
    fireEvent.pointerMove(div, { pointerId: 1, clientX: 40 })
    fireEvent.pointerMove(div, { pointerId: 1, clientX: 900 })
    fireEvent.pointerUp(div, { pointerId: 1, clientX: 900 })
    expect(loadIrcGutterPx()).toBe(IRC_GUTTER_MAX_PX)
    expect(loadIrcGutterPx()).toBeGreaterThanOrEqual(IRC_GUTTER_MIN_PX)
    view.unmount()
  })

  it('ignores moves with no active drag', () => {
    saveIrcGutterPx(140)
    const view = renderRow('irc')
    fireEvent.pointerMove(screen.getByTestId('irc-gutter-divider'), {
      pointerId: 1,
      clientX: 400,
    })
    expect(loadIrcGutterPx()).toBe(140)
    view.unmount()
  })

  it('double-click resets to the default', () => {
    localStorage.setItem(IRC_GUTTER_STORAGE_KEY, '300')
    const view = renderRow('irc')
    fireEvent.doubleClick(screen.getByTestId('irc-gutter-divider'))
    expect(loadIrcGutterPx()).toBe(IRC_GUTTER_DEFAULT_PX)
    view.unmount()
  })

  it('marks the divider while dragging (cursor/styling hook)', () => {
    const view = renderRow('irc')
    const div = screen.getByTestId('irc-gutter-divider')
    expect(div.getAttribute('data-dragging')).toBe('false')
    fireEvent.pointerDown(div, { pointerId: 1, clientX: 100 })
    expect(div.getAttribute('data-dragging')).toBe('true')
    fireEvent.pointerUp(div, { pointerId: 1, clientX: 120 })
    expect(div.getAttribute('data-dragging')).toBe('false')
    view.unmount()
  })
})
