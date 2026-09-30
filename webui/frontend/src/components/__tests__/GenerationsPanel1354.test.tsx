/**
 * #1354 — generations diagnostics finishing: Raw is expanded by default,
 * Escape closes with focus returned to the opener, and empty states are
 * honest rather than blank.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { GenerationsPanel, type PanelToolCall } from '../GenerationsPanel'

function rawPayload(over: Record<string, unknown> = {}) {
  return {
    conversation_id: 'conv-1',
    context: [
      { role: 'system', content: '[Conversation summary]\nEarlier chat.' },
      { role: 'user', content: 'latest question' },
    ],
    summaries_included: [1],
    summaries_excluded: [],
    cull_offset: 0,
    raw_turn_count: 2,
    ...over,
  }
}

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
      contexts={[{ id: 'conv-1', label: 'Current context' }]}
      activeContextId="conv-1"
      onSwitchContext={vi.fn()}
      toolCalls={[tool()]}
      {...props}
    />,
  )
}

describe('#1354 — GenerationsPanel diagnostics finishing', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => rawPayload(),
      } as Response),
    )
  })

  it('expands Raw by default — no second click required', async () => {
    renderPanel()
    const toggle = screen.getByTestId('generations-raw-toggle')
    expect(toggle).toHaveAttribute('aria-pressed', 'true')
    expect(await screen.findByTestId('generations-raw-view')).toHaveTextContent(
      'latest question',
    )
    expect(fetch).toHaveBeenCalledWith(
      '/chat/raw-context/?agent=codey&conversation_id=conv-1',
    )
  })

  it('Raw can still be collapsed and re-expanded', async () => {
    renderPanel()
    await screen.findByTestId('generations-raw-view')
    fireEvent.click(screen.getByTestId('generations-raw-toggle'))
    expect(screen.queryByTestId('generations-raw-view')).toBeNull()
    fireEvent.click(screen.getByTestId('generations-raw-toggle'))
    expect(await screen.findByTestId('generations-raw-view')).toBeInTheDocument()
  })

  it('shows an honest empty state when the context has no raw turns', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => rawPayload({ context: [], raw_turn_count: 0 }),
      } as Response),
    )
    renderPanel()
    expect(await screen.findByTestId('generations-raw-empty')).toHaveTextContent(
      /No raw model context/i,
    )
    expect(screen.queryByTestId('generations-raw-view')).toBeNull()
  })

  it('never crashes on a malformed intercepted payload — degrades honestly', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response),
    )
    renderPanel()
    expect(await screen.findByTestId('generations-raw-empty')).toBeInTheDocument()
  })

  it('keeps the honest tool-list empty state', () => {
    renderPanel({ toolCalls: [] })
    expect(screen.getByTestId('generations-tools-empty')).toHaveTextContent(
      /No tool calls in this context/i,
    )
  })

  it('Escape closes the panel', async () => {
    const onClose = vi.fn()
    renderPanel({ onClose })
    // Wait for the focus trap to seat focus inside the panel.
    await waitFor(() =>
      expect(screen.getByTestId('generations-panel')).toContainElement(
        document.activeElement as HTMLElement,
      ),
    )
    fireEvent.keyDown(document.activeElement as Element, { key: 'Escape' })
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('moves focus into the panel on open', async () => {
    renderPanel()
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByTestId('generations-close')),
    )
  })

  it('returns focus to the opener when closed', async () => {
    const opener = document.createElement('button')
    opener.textContent = 'opener'
    document.body.appendChild(opener)
    opener.focus()
    expect(document.activeElement).toBe(opener)
    const { unmount } = renderPanel()
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByTestId('generations-close')),
    )
    unmount()
    await waitFor(() => expect(document.activeElement).toBe(opener))
    opener.remove()
  })
})
