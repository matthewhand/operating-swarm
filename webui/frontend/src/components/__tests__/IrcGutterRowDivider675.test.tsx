/**
 * #721 (supersedes the #675 per-row presentation) — the IRC gutter divider is
 * ONE universal transcript-level rail, not a stack of per-row segments:
 *
 * 1. ChatMessageBubble renders NO per-row divider element.
 * 2. ChatPage renders exactly one `.os-irc-gutter-rail` inside the
 *    transcript (only for the irc theme), absolutely positioned at the
 *    shared `--irc-gutter-px` edge and spanning the full content.
 * 3. The rail keeps the #675 interaction contract: drag persists via the
 *    shared store, double-click resets to the default.
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { ChatMessageBubble } from '../ChatMessageBubble'
import { ToastProvider } from '../DaisyUI'
import {
  IRC_GUTTER_DEFAULT_PX,
  IRC_GUTTER_STORAGE_KEY,
  loadIrcGutterPx,
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

describe('#721 no per-row divider segments', () => {
  it('irc rows render no per-row divider element', () => {
    const { baseElement } = renderRow('irc')
    expect(within(baseElement).queryAllByTestId('irc-gutter-divider')).toHaveLength(0)
    expect(screen.queryByTestId('irc-gutter-divider')).toBeNull()
  })

  it('the per-row divider component code is gone from ChatMessageBubble', () => {
    const src = readFileSync(join(process.cwd(), 'src/components/ChatMessageBubble.tsx'), 'utf8')
    expect(src).not.toContain('os-irc-gutter-divider')
    expect(src).not.toContain('onIrcDividerPointerDown')
  })

  it('the rail css anchors to the shared var, full height, drag handle', () => {
    const css = readFileSync(join(process.cwd(), 'src/index.css'), 'utf8')
    const block = css.match(/\.os-irc-gutter-rail \{[^}]*\}/)?.[0] ?? ''
    expect(block).toContain('position: absolute')
    expect(block).toContain('top: 0')
    expect(block).toContain('bottom: 0')
    expect(block).toContain('var(--irc-gutter-px)')
    expect(block).toContain('col-resize')
  })
})

describe('#721 rail interaction contract (kept from #675)', () => {
  it('dragging the rail persists a clamped width through the shared store', async () => {
    const { default: ChatPage } = await import('../../pages/ChatPage')
    const { QueryClient, QueryClientProvider } = await import('@tanstack/react-query')
    const { MemoryRouter } = await import('react-router-dom')
    const { saveBubbleTheme } = await import('../../lib/bubbleTheme')
    saveBubbleTheme('irc')
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const view = render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat?blueprint=support']}>
            <ChatPage />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )
    const rail = await screen.findByTestId('irc-gutter-rail')
    const { baseElement } = view
    expect(within(baseElement).getAllByTestId('irc-gutter-rail')).toHaveLength(1)
    rail.dispatchEvent(new window.PointerEvent('pointerdown', { bubbles: true, clientX: 200, pointerId: 1 }))
    fireEvent(rail, new window.PointerEvent('pointermove', { bubbles: true, clientX: 340, pointerId: 1 }))
    rail.dispatchEvent(new window.PointerEvent('pointerup', { bubbles: true, clientX: 340, pointerId: 1 }))
    expect(loadIrcGutterPx()).toBe(280) // 140 start + (340-200) delta
  })

  it('double-click resets to the default', async () => {
    const { default: ChatPage } = await import('../../pages/ChatPage')
    const { QueryClient, QueryClientProvider } = await import('@tanstack/react-query')
    const { MemoryRouter } = await import('react-router-dom')
    const { saveBubbleTheme } = await import('../../lib/bubbleTheme')
    saveBubbleTheme('irc')
    localStorage.setItem(IRC_GUTTER_STORAGE_KEY, '300')
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat?blueprint=support']}>
            <ChatPage />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )
    const rail = await screen.findByTestId('irc-gutter-rail')
    fireEvent.doubleClick(rail)
    expect(loadIrcGutterPx()).toBe(IRC_GUTTER_DEFAULT_PX)
  })
})
