/**
 * #1121 — an agent's bubble-theme override must reach the transcript.
 *
 * The regression: ChatPage rendered only the *global* theme
 * (`os.bubbleTheme`), so `setAgentBubbleTheme` (rail menu → theme) persisted
 * the override and dispatched the change event — and the open transcript
 * still showed the old theme. Contracts pinned here:
 *
 * 1. Override present before mount → transcript renders the override.
 * 2. `setAgentBubbleTheme` while mounted → `data-bubble-theme` flips on the
 *    very next render (no reload, no chat switch).
 * 3. A global theme change does NOT override an existing per-agent override
 *    (precedence: agent override wins for that agent's transcript).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '../../components/DaisyUI'
import ChatPage from '../ChatPage'
import {
  AGENT_BUBBLE_THEME_STORAGE_KEY,
  BUBBLE_THEME_STORAGE_KEY,
  saveBubbleTheme,
  setAgentBubbleTheme,
} from '../../lib/bubbleTheme'

function renderChat() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={['/chat?blueprint=support']}>
          <ChatPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

function transcript() {
  return screen.getByRole('log', { name: 'Conversation' })
}

describe('#1121: per-agent bubble-theme override reaches the transcript', () => {
  beforeEach(() => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
    localStorage.removeItem(BUBBLE_THEME_STORAGE_KEY)
    localStorage.removeItem(AGENT_BUBBLE_THEME_STORAGE_KEY)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/blueprints')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              data: [{ id: 'support', name: 'Support', description: 'Support agent' }],
            }),
          } as Response
        }
        return { ok: true, status: 200, json: async () => ({ data: [] }) } as Response
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    localStorage.removeItem(BUBBLE_THEME_STORAGE_KEY)
    localStorage.removeItem(AGENT_BUBBLE_THEME_STORAGE_KEY)
  })

  it('override present before mount renders on the transcript', () => {
    saveBubbleTheme('speech')
    setAgentBubbleTheme('support', 'irc')
    renderChat()
    expect(transcript()).toHaveAttribute('data-bubble-theme', 'irc')
  })

  it('setAgentBubbleTheme while mounted restyles immediately', () => {
    saveBubbleTheme('speech')
    renderChat()
    expect(transcript()).toHaveAttribute('data-bubble-theme', 'speech')

    act(() => {
      setAgentBubbleTheme('support', 'irc')
    })
    expect(transcript()).toHaveAttribute('data-bubble-theme', 'irc')

    act(() => {
      setAgentBubbleTheme('support', null)
    })
    expect(transcript()).toHaveAttribute('data-bubble-theme', 'speech')
  })

  it('a global theme change does not clobber an existing override', () => {
    saveBubbleTheme('speech')
    renderChat()
    act(() => {
      setAgentBubbleTheme('support', 'irc')
    })
    expect(transcript()).toHaveAttribute('data-bubble-theme', 'irc')

    act(() => {
      saveBubbleTheme('simple')
    })
    // agent override still wins for this agent's transcript
    expect(transcript()).toHaveAttribute('data-bubble-theme', 'irc')
  })
})
