/**
 * #675 — the IRC theme's resizable gutter.
 *
 * The transcript root publishes the persisted width as `--irc-gutter-px` so
 * every message body starts at the same x (classic IRC alignment). Changes
 * come from the per-row dividers (tested at the lib + row level); this page
 * contract pins the two outcomes that matter:
 *   1. the CSS var reflects the persisted preference (loaded, not default),
 *   2. a store change re-syncs the var live — the transcript moves while
 *      any divider is dragged.
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import {
  IRC_GUTTER_CHANGED_EVENT,
  IRC_GUTTER_STORAGE_KEY,
  saveIrcGutterPx,
} from '../../lib/ircGutter'
import { saveBubbleTheme } from '../../lib/bubbleTheme'

beforeEach(() => {
  localStorage.clear()
})

async function renderPage(theme: string) {
  saveBubbleTheme(theme)
  const { default: ChatPage } = await import('../ChatPage')
  const { QueryClient, QueryClientProvider } = await import('@tanstack/react-query')
  const { MemoryRouter } = await import('react-router-dom')
  const { ToastProvider } = await import('../../components/DaisyUI')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={['/chat?blueprint=support']}>
          <ChatPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

function transcript(): HTMLElement {
  return document.querySelector('.os-chat-transcript') as HTMLElement
}

describe('#675 IRC gutter — transcript CSS var sync', () => {
  it('exposes the persisted width as --irc-gutter-px on the transcript', async () => {
    localStorage.setItem(IRC_GUTTER_STORAGE_KEY, '220')
    await renderPage('irc')
    expect(transcript().style.getPropertyValue('--irc-gutter-px')).toBe('220px')
    screen.getByTestId('chat-messages-container')
  })

  it('re-syncs the var when the store changes (live drag)', async () => {
    await renderPage('irc')
    expect(transcript().style.getPropertyValue('--irc-gutter-px')).toBe('140px')
    saveIrcGutterPx(260)
    act(() => {
      window.dispatchEvent(new CustomEvent(IRC_GUTTER_CHANGED_EVENT))
    })
    expect(transcript().style.getPropertyValue('--irc-gutter-px')).toBe('260px')
  })

  it('other themes do not set the var', async () => {
    await renderPage('speech')
    expect(transcript().style.getPropertyValue('--irc-gutter-px')).toBe('')
  })
})
