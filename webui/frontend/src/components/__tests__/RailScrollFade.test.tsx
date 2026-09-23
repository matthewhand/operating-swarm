import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import AgentSidebar from '../AgentSidebar'

/** Seed the react-query cache the sidebar actually reads (GET /v1/blueprints/). */
function seedBlueprints(queryClient: QueryClient, blueprints: unknown[]) {
  queryClient.setQueryData(['blueprints'], { data: blueprints })
}

describe('AgentSidebar Rail Scroll Fade (REQ-99)', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })
  })

  it('renders fade, plugins button opens modal', () => {
    seedBlueprints(queryClient, [
      {
        id: 'support_agent',
        object: 'blueprint' as const,
        name: 'Support Agent',
        description: 'Customer help',
        abbreviation: null,
        required_mcp_servers: [],
        tags: [],
        role: 'support',
        installed: true,
        compiled: true,
      },
      {
        id: 'codey',
        object: 'blueprint' as const,
        name: 'Codey',
        description: 'Code assistant',
        abbreviation: null,
        required_mcp_servers: [],
        tags: [],
        role: 'default',
        installed: true,
        compiled: true,
      },
    ])

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AgentSidebar open />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const fade = screen.getByTestId('rail-scroll-fade')
    expect(fade).toBeInTheDocument()
    expect(fade).toHaveClass('os-rail-scroll-fade')
    expect(fade).toHaveClass('pointer-events-none')

    // Plugins button is clickable and opens modal
    const pluginsBtn = screen.getByRole('button', { name: 'Plugins' })
    expect(pluginsBtn).toBeInTheDocument()
    fireEvent.click(pluginsBtn)
    expect(screen.getByRole('dialog', { name: 'Plugins' })).toBeInTheDocument()
  })

  it('activates fade opacity when scrollable list can scroll', () => {
    seedBlueprints(queryClient, [
      {
        id: 'support_agent',
        object: 'blueprint' as const,
        name: 'Support Agent',
        description: 'Customer help',
        abbreviation: null,
        required_mcp_servers: [],
        tags: [],
        role: 'support',
        installed: true,
        compiled: true,
      },
    ])

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AgentSidebar open />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const nav = screen.getByRole('navigation', { name: 'Agent list' })
    const fade = screen.getByTestId('rail-scroll-fade')

    // Simulate overflow
    Object.defineProperty(nav, 'scrollHeight', { value: 600, configurable: true })
    Object.defineProperty(nav, 'clientHeight', { value: 200, configurable: true })
    fireEvent.scroll(nav)

    expect(fade).toHaveAttribute('data-can-scroll', 'true')
    expect(fade).toHaveClass('opacity-100')
  })
})
