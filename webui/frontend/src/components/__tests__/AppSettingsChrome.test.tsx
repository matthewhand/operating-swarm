import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../../App'

async function renderApp() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  Element.prototype.scrollIntoView = vi.fn()
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ data: [] }),
    } as Response),
  )
  const view = render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
  // #1629: the chat surface is a lazy chunk now; wait for the first painted
  // frame (including ChatHeader) instead of racing the dynamic import.
  await screen.findByRole('button', { name: 'Open settings' })
  await waitFor(() => {
    expect(document.querySelector('[data-testid="os-agent-rail"]')).not.toBeNull()
  })
  return view
}

describe('#816 sidepane placement', () => {
  afterEach(() => {
    localStorage.clear()
  })

  it('settings sheet mirrors to the opposite edge of the rail', async () => {
    localStorage.setItem('swarm_rail_side', 'right')
    await renderApp()
    fireEvent.click(screen.getByRole('button', { name: 'Open settings' }))
    const dialog = await screen.findByRole('dialog', { name: 'Settings', hidden: true })
    expect(dialog).toHaveClass('modal-start')
  })

  it('the rail layout flips when the preference is right', async () => {
    localStorage.setItem('swarm_rail_side', 'right')
    await renderApp()
    expect(document.querySelector('[data-testid="os-agent-rail"]')).toHaveClass(
      'os-agent-sidebar--right',
    )
    // flex-row-reverse mirrors the VISUAL order (rail renders on the right).
    const row = document.querySelector('div.flex-row-reverse')!
    expect(row).toBeInTheDocument()
    expect(row).toContainElement(document.querySelector('aside.os-agent-sidebar'))
  })

  it('the Rail pane toggle persists the side via the announced event', async () => {
    await renderApp()
    fireEvent.click(screen.getByRole('button', { name: 'Open settings' }))
    const dialog = await screen.findByRole('dialog', { name: 'Settings', hidden: true })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Rail' }))
    const rightBtn = await screen.findByTestId('rail-side-right')
    expect(rightBtn).toBeInTheDocument()
    fireEvent.click(rightBtn)
    expect(localStorage.getItem('swarm_rail_side')).toBe('right')
  })
})

describe('SPA settings chrome (REQ-19)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('opens a modal-end sheet from the gear and keeps Settings out of Grok chrome', async () => {
    await renderApp()

    // 322 chrome: left rail + chat, no product top-nav / mobile dock.
    expect(screen.queryByRole('navigation', { name: 'Primary' })).not.toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Mobile primary' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /^Settings$/i })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Open settings' }))
    const dialog = await screen.findByRole('dialog', { name: 'Settings', hidden: true })
    expect(dialog).toHaveClass('modal-end')
    expect(dialog).toHaveClass('modal-open')
    expect(screen.getByRole('navigation', { name: 'Settings sections' })).toBeInTheDocument()
    // REQ-48: Settings is a sheet over chat, not a route that unmounts the composer.
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
  })

  it('REQ-19 #334: swarm:open-settings with a blueprintId opens the Blueprint pane', async () => {
    await renderApp()
    window.dispatchEvent(
      new CustomEvent('swarm:open-settings', {
        detail: { section: 'blueprint', blueprintId: 'support' },
      }),
    )
    const dialog = await screen.findByRole('dialog', { name: 'Settings', hidden: true })
    expect(dialog).toHaveClass('modal-open')
    expect(screen.getByRole('button', { name: 'Blueprints' })).toHaveClass('menu-active')
    expect(screen.getByRole('heading', { name: 'Blueprints' })).toBeInTheDocument()
  })

  it('REQ-54: mobile chrome has no hamburger and no product dock', async () => {
    await renderApp()
    expect(screen.queryByRole('button', { name: 'Open agents sidebar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Mobile primary' })).not.toBeInTheDocument()
  })
})
