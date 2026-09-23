import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import AgentSidebar from '../AgentSidebar'

/** Seed the react-query cache the sidebar actually reads (GET /v1/blueprints/). */
function seedBlueprints(queryClient: QueryClient, blueprints: unknown[]) {
  queryClient.setQueryData(['blueprints'], { data: blueprints })
}

describe('AgentSidebar No Pencils (REQ-173)', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })
  })

  it('renders agent rows without hover pencil edit buttons', () => {
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

    // Verify no pencil edit buttons are rendered in the sidebar rows
    expect(screen.queryByLabelText(/Edit Support Agent/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Edit Codey/i)).not.toBeInTheDocument()
    expect(document.querySelector('.os-agent-edit')).not.toBeInTheDocument()
  })
})
