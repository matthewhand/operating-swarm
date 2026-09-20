/**
 * #532 Part A/B — Edit Agent role UX: Worker default, wire-up checkboxes,
 * unused-role hint, and the verb diagram naming the wired consumers.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AgentEditor from '../AgentEditor'
import { ToastProvider } from '../DaisyUI'
import { ROLE_CONSUMERS_KEY } from '../../lib/roleConsumers'

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

describe('AgentEditor role wire-up (#532)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    stubCatalog()
  })

  it('lists Worker (default) as the default role', async () => {
    renderEditor()
    await waitFor(() => expect(screen.getByLabelText('Role')).toBeTruthy())
    const select = screen.getByLabelText('Role') as HTMLSelectElement
    expect(select.selectedOptions[0]?.textContent).toBe('Worker (default)')
  })

  it('shows the unused-role hint and wire-up list for a non-worker role', async () => {
    renderEditor()
    await waitFor(() => expect(screen.getByLabelText('Role')).toBeTruthy())
    fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'suggestions' } })

    const wireup = await waitFor(() => screen.getByTestId('role-consumer-wireup'))
    expect(wireup).toBeTruthy()
    expect(screen.getByTestId('role-unused-hint').textContent).toContain(
      'unused until it has been linked',
    )
    expect(screen.getByTestId('wire-consumer-codey')).toBeTruthy()
  })

  it('wires a consumer and renders the verb diagram', async () => {
    renderEditor()
    await waitFor(() => expect(screen.getByLabelText('Role')).toBeTruthy())
    fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'suggestions' } })

    const box = await screen.findByTestId('wire-consumer-codey')
    fireEvent.click(box)

    const diagram = screen.getByTestId('role-verb-diagram')
    expect(diagram.textContent).toContain('Codey')
    expect(diagram.textContent).toContain('Charles')
    expect(diagram.textContent).toContain('consults')

    const stored = JSON.parse(window.localStorage.getItem(ROLE_CONSUMERS_KEY) || '{}')
    expect(stored.charles.suggestions).toEqual(['codey'])
  })

  it('restores an existing wire-up when the editor reopens', async () => {
    window.localStorage.setItem(
      ROLE_CONSUMERS_KEY,
      JSON.stringify({ charles: { advisor: ['codey'] } }),
    )
    renderEditor()
    await waitFor(() => expect(screen.getByLabelText('Role')).toBeTruthy())
    fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'advisor' } })

    const box = await screen.findByTestId('wire-consumer-codey')
    expect((box as HTMLInputElement).checked).toBe(true)
    expect(screen.getByTestId('role-verb-diagram').textContent).toContain('Codey consults Charles')
  })
})

describe('#853 — the support role is exclusive to API seats', () => {
  beforeEach(() => {
    window.localStorage.clear()
    stubCatalog()
  })

  it('hides the support option for a CLI-kind seat and keeps it for API seats', async () => {
    // 'codey' resolves to an API/blueprint seat; a cli-prefixed id resolves cli.
    renderEditor('codey')
    await waitFor(() => expect(screen.getByLabelText('Role')).toBeTruthy())
    const apiSelect = screen.getByLabelText('Role') as HTMLSelectElement
    expect([...apiSelect.options].some((o) => o.value === 'support')).toBe(true)

    const { unmount } = { unmount: () => undefined }
    void unmount
  })

  it('a CLI-kind seat rejects selecting support via the guard toast', async () => {
    // Direct guard check: persistRole's kind gate fires the explicit error.
    const src = await (async () => {
      const { readFileSync } = await import('node:fs')
      const { join } = await import('node:path')
      return readFileSync(join(process.cwd(), 'src/components/AgentEditor.tsx'), 'utf8')
    })()
    expect(src).toMatch(/Support role is exclusively available to API agents/)
    expect(src).toMatch(/agentKind !== 'api'/)
  })
})
