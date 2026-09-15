import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { GenerationsPanel, type PanelToolCall } from '../GenerationsPanel'

const CONTEXTS = [
  { id: 'conv-1', label: 'Current context' },
  { id: 'conv-0', label: 'Earlier context' },
]

function tool(overrides: Partial<PanelToolCall> = {}): PanelToolCall {
  return { id: 't1', name: 'read_file', status: 'done', ...overrides }
}

function renderPanel(props: Partial<Parameters<typeof GenerationsPanel>[0]> = {}) {
  return render(
    <GenerationsPanel
      open={true}
      onClose={vi.fn()}
      agentId="codey"
      agentName="Codey"
      contexts={CONTEXTS}
      activeContextId="conv-1"
      onSwitchContext={vi.fn()}
      toolCalls={[tool()]}
      {...props}
    />,
  )
}

describe('GenerationsPanel (#224)', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          conversation_id: 'conv-1',
          context: [
            { role: 'system', content: '[Conversation summary]\nEarlier chat.' },
            { role: 'user', content: 'latest question' },
          ],
          summaries_included: [1],
          summaries_excluded: [],
          cull_offset: 0,
          raw_turn_count: 2,
        }),
      } as Response),
    )
  })

  it('renders nothing when closed', () => {
    const { container } = renderPanel({ open: false })
    expect(container).toBeEmptyDOMElement()
  })

  it('lists tool calls collapsed; expand/collapse-all and per-call toggle work', () => {
    const tools = [tool(), tool({ id: 't2', name: 'web_search', status: 'running' })]
    renderPanel({ toolCalls: tools })
    expect(screen.getAllByTestId('generations-tool')).toHaveLength(2)
    expect(screen.queryByTestId('generations-tool-body-t1')).toBeNull()

    fireEvent.click(screen.getByTestId('generations-expand-all'))
    expect(screen.getByTestId('generations-tool-body-t1')).toBeTruthy()
    expect(screen.getByTestId('generations-tool-body-t2')).toBeTruthy()

    fireEvent.click(screen.getByTestId('generations-collapse-all'))
    expect(screen.queryByTestId('generations-tool-body-t1')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /read_file/i }))
    expect(screen.getByTestId('generations-tool-body-t1')).toBeTruthy()
  })

  it('is honest when the backend sent no args/output', () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('generations-expand-all'))
    expect(
      screen.getByText(/Args\/output not sent by this tool event yet/i),
    ).toBeInTheDocument()
  })

  it('shows args/output when the tool event carries them', () => {
    renderPanel({
      toolCalls: [tool({ args: { path: 'src/app.ts' }, output: 'export const x = 1' })],
    })
    fireEvent.click(screen.getByTestId('generations-expand-all'))
    const body = screen.getByTestId('generations-tool-body-t1')
    expect(body).toHaveTextContent('src/app.ts')
    expect(body).toHaveTextContent('export const x = 1')
  })

  it('Raw view fetches the model context and renders it read-only', async () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('generations-raw-toggle'))
    await waitFor(() => {
      expect(screen.getByTestId('generations-raw-view')).toBeTruthy()
    })
    expect(fetch).toHaveBeenCalledWith(
      '/chat/raw-context/?agent=codey&conversation_id=conv-1',
    )
    const raw = screen.getByTestId('generations-raw-view')
    expect(raw.textContent).toContain('[Conversation summary]')
    expect(raw.textContent).toContain('latest question')
    expect(screen.getByTestId('generations-raw-meta')).toHaveTextContent('2 raw turns')
  })

  it('Raw fetch errors surface honestly instead of fabricated context', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 500 } as Response),
    )
    renderPanel()
    fireEvent.click(screen.getByTestId('generations-raw-toggle'))
    expect(await screen.findByTestId('generations-raw-error')).toHaveTextContent(
      'HTTP 500',
    )
    expect(screen.queryByTestId('generations-raw-view')).toBeNull()
  })

  it('context switcher renders when multiple contexts exist and marks the active one', () => {
    renderPanel()
    const tabs = screen.getAllByRole('tab')
    expect(tabs).toHaveLength(2)
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
    expect(tabs[1]).toHaveAttribute('aria-selected', 'false')
  })
})
