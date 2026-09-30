import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, fireEvent, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ToastProvider } from '../../components/DaisyUI'
import ChatPage from '../ChatPage'
import * as agentEditorModule from '../../lib/agentSettings'
import { OPEN_GENERATIONS_EVENT } from '../../components/settings/generationsEntry'
import { declaration, readCssSource } from '../../lib/__tests__/helpers/cssRules'

/**
 * The identity card's own chrome used to be asserted as four DaisyUI utility
 * classes on the element:
 *
 *   expect(card).toHaveClass('border-transparent')
 *   expect(card).toHaveClass('hover:bg-base-200/50')
 *   expect(card).toHaveClass('hover:border-base-content/10')
 *
 * #1676 restyled the pill: the border, background and hover treatment moved out
 * of Tailwind utilities and into the `.os-agent-pill` rule in `index.css`
 * (`border: 1px solid color-mix(...)`, `background: color-mix(...)`, and a
 * `:hover` rule that changes both). The utilities were deleted because the
 * sheet now owns that surface, and this test went red on a correct restyle.
 *
 * These class assertions could not have detected the property anyway: a
 * `border-transparent` utility says nothing about whether the pill's border
 * actually renders, and it cannot see the `.os-agent-pill` rule at all. What
 * follows asserts the real thing -- the element carries the hook class, and the
 * sheet gives that hook a themed border, a themed background, and a hover
 * state that changes them. jsdom computes no layout, so the stylesheet is read
 * as parsed rules; `features/chat/__tests__/ChatHeader.agentPill1676.test.tsx`
 * covers the same rule's token-only constraint from the component side.
 */
const css = readCssSource()

class MockWebSocket {
  static instances: MockWebSocket[] = []
  url: string
  readyState = 0
  onopen: ((e?: unknown) => void) | null = null
  onclose: ((e?: unknown) => void) | null = null
  onmessage: ((e: MessageEvent) => void) | null = null
  send = vi.fn()
  close = vi.fn()

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  open() {
    this.readyState = 1
    this.onopen?.()
  }
}


describe('REQ-214: Navbar agent identity hover card', () => {
  beforeEach(() => {
    localStorage.clear()
    Element.prototype.scrollIntoView = vi.fn()
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ results: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders hover card wrapping avatar, name, and pencil; avatar does not open the editor', async () => {
    const openEditorSpy = vi.spyOn(agentEditorModule, 'openAgentEditor')

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat?blueprint=support']}>
            <ChatPage />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )

    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const card = screen.getByTestId('selected-agent-header')
    expect(card).toHaveClass('os-navbar-identity-card')
    // #1676: the pill hook that owns the border/background/hover treatment in
    // index.css. Asserting the hook, then asserting the sheet's rule for it,
    // is what the four deleted DaisyUI utility assertions were reaching for.
    expect(card).toHaveClass('os-agent-pill')

    // The card's chrome is a themed border and a themed background -- not a
    // hard-coded one, so it reads correctly in both DaisyUI themes.
    const border = declaration(css, '.os-agent-pill', 'border')
    expect(border, '.os-agent-pill has no border declaration').toBeTruthy()
    expect(border).toContain('var(--color-base-content)')
    const background = declaration(css, '.os-agent-pill', 'background')
    expect(background, '.os-agent-pill has no background declaration').toBeTruthy()
    expect(background).toContain('var(--color-base-100)')

    // Hover must actually change both, or the card is not a hover card.
    const hoverBorder = declaration(css, '.os-agent-pill:hover', 'border-color')
    const hoverBackground = declaration(css, '.os-agent-pill:hover', 'background')
    expect(hoverBorder, '.os-agent-pill:hover has no border-color change').toBeTruthy()
    expect(hoverBackground, '.os-agent-pill:hover has no background change').toBeTruthy()
    expect(hoverBorder).not.toBe(border)
    expect(hoverBackground).not.toBe(background)
    // Keyboard parity: focusing anything inside the card also reveals it.
    expect(declaration(css, '.os-agent-pill:focus-within', 'border-color')).toBeTruthy()

    expect(card).toHaveAttribute('role', 'group')
    expect(card).not.toHaveAttribute('role', 'button')

    // Avatar, name, and pencil are inside the card
    const avatar = card.querySelector('.os-chat-header__avatar')
    expect(avatar).toBeInTheDocument()
    expect(card).toHaveTextContent('Support')
    const pencil = card.querySelector('.os-navbar-edit-btn')
    expect(pencil).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('header-avatar-generations'))
    expect(openEditorSpy).not.toHaveBeenCalled()
    // #1258: the avatar opens agent configuration — never generations.
    expect(screen.getByTestId('agent-config-sidepane')).toBeInTheDocument()
    expect(screen.queryByTestId('generations-panel')).toBeNull()

    // #1354: the diagnostics entry moved to Settings; the sheet dispatches
    // this event and the mounted chat header opens the panel.
    await act(async () => {
      window.dispatchEvent(new CustomEvent(OPEN_GENERATIONS_EVENT))
    })
    expect(await screen.findByTestId('generations-panel')).toBeInTheDocument()

    openEditorSpy.mockClear()
    fireEvent.click(card)
    expect(openEditorSpy).not.toHaveBeenCalled()

    fireEvent.click(within(card).getByRole('button', { name: 'Edit agent' }))
    expect(openEditorSpy).toHaveBeenCalledWith(
      expect.objectContaining({ agentId: 'support' })
    )

    openEditorSpy.mockRestore()
  })
})
