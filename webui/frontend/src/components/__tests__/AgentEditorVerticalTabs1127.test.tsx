/**
 * #1127 — the Edit Agent editor is a vertical-tab surface, not an endless stack.
 *
 * The editor had grown to ~18 stacked sections (role picker, #532 wiring,
 * LLM overrides, voice, toggles…) requiring a long scroll. The sections are
 * now grouped into four tab panels with a vertical tab rail (the editor is
 * tall, not wide):
 *
 *   Identity          — name, avatar, persona avatars
 *   Role & wiring     — the #532 role picker, wire-up, mailbox ACL
 *   Model & inference — blueprint, inference order, per-kind LLM override
 *   Advanced          — skills, voice, workspace, toggles, context detail
 *
 * Inactive panels stay mounted-but-hidden so in-progress edits and the
 * hydration contract (#592) survive tab switches. The selected tab persists
 * across open/close within the session.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AgentEditor from '../AgentEditor'
import { ToastProvider } from '../DaisyUI'

const catalog = [
  {
    id: 'charles',
    object: 'blueprint' as const,
    name: 'Charles',
    description: 'Suggestions provider',
    abbreviation: null,
    required_mcp_servers: [] as string[],
    tags: [] as string[],
    installed: true,
    compiled: true,
  },
  {
    id: 'codey',
    object: 'blueprint' as const,
    name: 'Codey',
    description: 'Worker seat',
    abbreviation: null,
    required_mcp_servers: [] as string[],
    tags: [] as string[],
    installed: true,
    compiled: true,
  },
]

function stubCatalog() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/v1/blueprints') && url.includes('/source')) {
        return {
          ok: false,
          status: 404,
          json: async () => ({ error: 'blueprint not found' }),
        } as Response
      }
      if (url.includes('/v1/agents/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            new_chat_per_task: false,
            use_suggestions: false,
            folder: '',
          }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: catalog }),
      } as Response
    }),
  )
}

function renderEditor(agentId = 'charles') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AgentEditor isOpen onClose={vi.fn()} agentId={agentId} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  stubCatalog()
  sessionStorage.clear()
})

describe('#1127 vertical tab rail', () => {
  it('renders a vertical tablist with the four section tabs', () => {
    renderEditor()
    const rail = screen.getByTestId('agent-editor-tabs')
    expect(rail).toHaveAttribute('role', 'tablist')
    expect(rail).toHaveAttribute('aria-orientation', 'vertical')
    const tabs = within(rail).getAllByRole('tab')
    expect(tabs.map((tab) => tab.textContent)).toEqual([
      'Identity',
      'Role & wiring',
      'Model & inference',
      'Advanced',
    ])
  })

  it('opens on Identity: name is visible with no clicks, avatar panel active', () => {
    renderEditor()
    // Name is the editor's primary field — shared header, always visible.
    expect(screen.getByLabelText('Name')).toBeVisible()
    const avatarPanel = screen
      .getByTestId('agent-editor-avatar')
      .closest('[role="tabpanel"]')
    expect(avatarPanel).toHaveAttribute('aria-labelledby', 'agent-editor-tab-identity')
    expect(avatarPanel).not.toHaveAttribute('hidden')
  })

  it('switching tabs reveals that panel and hides the others', () => {
    renderEditor()
    fireEvent.click(within(screen.getByTestId('agent-editor-tabs')).getByRole('tab', { name: 'Advanced' }))
    const voicePanel = screen.getByLabelText('Speech mode').closest('[role="tabpanel"]')
    expect(voicePanel).not.toHaveAttribute('hidden')
    const rolePanel = screen.getByLabelText('Role').closest('[role="tabpanel"]')
    expect(rolePanel).toHaveAttribute('hidden')
  })

  it('selected tab persists across close/reopen within the session', () => {
    const first = renderEditor()
    fireEvent.click(within(screen.getByTestId('agent-editor-tabs')).getByRole('tab', { name: 'Model & inference' }))
    first.unmount()
    renderEditor()
    const active = within(screen.getByTestId('agent-editor-tabs')).getByRole('tab', { selected: true })
    expect(active).toHaveTextContent('Model & inference')
  })
})

describe('#1127 section placement (contracts preserved)', () => {
  it('Role & wiring owns the #532 picker, explanation, and wire-up', async () => {
    renderEditor('charles')
    fireEvent.click(within(screen.getByTestId('agent-editor-tabs')).getByRole('tab', { name: 'Role & wiring' }))
    const rolePanel = screen.getByLabelText('Role').closest('[role="tabpanel"]')
    expect(rolePanel).not.toHaveAttribute('hidden')
    expect(within(rolePanel as HTMLElement).getByTestId('role-explanation')).toBeInTheDocument()
    // Worker default: no wire-up block on the default role.
    expect(within(rolePanel as HTMLElement).queryByTestId('role-consumer-wireup')).toBeNull()
    // Non-worker role reveals the #532 wire-up inside the same panel.
    fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'suggestions' } })
    await waitFor(() => {
      expect(screen.getByTestId('role-consumer-wireup')).toBeInTheDocument()
    })
    expect(screen.getByTestId('role-consumer-wireup').closest('[role="tabpanel"]')).toBe(rolePanel)
  })

  it('Model & inference owns the blueprint picker; overrides live in Advanced', () => {
    renderEditor('codey')
    fireEvent.click(within(screen.getByTestId('agent-editor-tabs')).getByRole('tab', { name: 'Model & inference' }))
    const blueprint = screen.getByLabelText('Blueprint')
    const panel = blueprint.closest('[role="tabpanel"]')
    expect(panel).not.toHaveAttribute('hidden')
    // The per-kind provider/model override is reachable under Advanced.
    fireEvent.click(within(screen.getByTestId('agent-editor-tabs')).getByRole('tab', { name: 'Advanced' }))
    const advancedPanel = screen.getByLabelText('Speech mode').closest('[role="tabpanel"]')
    expect(within(advancedPanel as HTMLElement).getAllByText(/LLM override/i).length).toBeGreaterThan(0)
  })

  it('Identity owns the avatar editor', () => {
    renderEditor('charles')
    expect(screen.getByTestId('agent-editor-avatar').closest('[role="tabpanel"]')).not.toHaveAttribute('hidden')
  })
})
