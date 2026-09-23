import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BlueprintEditorPane } from '../SettingsSheet'
import { ToastProvider } from '../DaisyUI'

function renderEditor(blueprintId: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <BlueprintEditorPane blueprintId={blueprintId} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

const CUSTOM_SOURCE = {
  id: 'my_custom_agent',
  files: [{ name: 'blueprint_my_custom_agent.py', path: 'blueprint_my_custom_agent.py' }],
  primary: 'blueprint_my_custom_agent.py',
  selected: 'blueprint_my_custom_agent.py',
  content: 'class Ok:\n    pass\n',
  editable: true,
  origin: 'custom',
  readonly_reason: null,
}

describe('REQ-211: Settings Blueprints inline edit + save', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses a real textarea and Save for writable custom source', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(CUSTOM_SOURCE)),
    )
    renderEditor('my_custom_agent')
    const editor = await screen.findByRole('textbox', { name: /my_custom_agent blueprint Python/i })
    expect(editor.tagName).toBe('TEXTAREA')
    expect(editor).not.toHaveAttribute('readonly')
    const desc = screen.getByText(/Editing/i)
    expect(desc).toHaveTextContent('Editing')
    expect(screen.getByRole('button', { name: /^Save$/ })).toBeInTheDocument()
    expect(screen.queryByText(/Viewing/i)).toBeNull()
  })

  it('persists Save and reloads the updated source', async () => {
    let content = CUSTOM_SOURCE.content
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
      const url = String(input)
      if ((init?.method || 'GET') === 'PUT' && url.includes('/source')) {
        const body = JSON.parse(String(init?.body || '{}')) as { content?: string }
        content = body.content || content
        return jsonResponse({
          ...CUSTOM_SOURCE,
          content,
        })
      }
      return jsonResponse({ ...CUSTOM_SOURCE, content })
    })
    vi.stubGlobal('fetch', fetchMock)
    renderEditor('my_custom_agent')
    const editor = await screen.findByRole('textbox', { name: /my_custom_agent blueprint Python/i })
    fireEvent.change(editor, { target: { value: 'class Saved:\n    pass\n' } })
    fireEvent.click(screen.getByRole('button', { name: /^Save$/ }))
    await waitFor(() => {
      expect(screen.getByText(/Saved\. Reloaded as the updated blueprint/i)).toBeInTheDocument()
    })
    expect(fetchMock.mock.calls.some(([input, init]) => (
      String(input).includes('/v1/blueprints/my_custom_agent/source')
      && (init as RequestInit | undefined)?.method === 'PUT'
    ))).toBe(true)
    expect((editor as HTMLTextAreaElement).value).toContain('class Saved')
  })

  it('rejects invalid Python with a clear error and keeps the prior draft', async () => {
    const fetchMock = vi.fn().mockImplementation(async (_input: RequestInfo, init?: RequestInit) => {
      if ((init?.method || 'GET') === 'PUT') {
        return jsonResponse({ error: 'Invalid Python syntax: invalid syntax at line 1' }, 400)
      }
      return jsonResponse(CUSTOM_SOURCE)
    })
    vi.stubGlobal('fetch', fetchMock)
    renderEditor('my_custom_agent')
    const editor = await screen.findByRole('textbox', { name: /my_custom_agent blueprint Python/i })
    fireEvent.change(editor, { target: { value: 'def (\n' } })
    fireEvent.click(screen.getByRole('button', { name: /^Save$/ }))
    await waitFor(() => {
      expect(screen.getByText(/Invalid Python syntax/i)).toBeInTheDocument()
    })
    expect(screen.queryByText(/Saved\./i)).toBeNull()
    expect((editor as HTMLTextAreaElement).value).toBe('def (\n')
  })

  it('keeps bundled recipes Viewing with no Save', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          id: 'support',
          files: [{ name: 'blueprint_support.py', path: 'blueprint_support.py' }],
          primary: 'blueprint_support.py',
          selected: 'blueprint_support.py',
          content: 'def ask_user(question):\n    return question\n',
          editable: false,
          origin: 'bundled',
          readonly_reason: 'Bundled checkout recipe — not writable from Settings or the library.',
        }),
      ),
    )
    renderEditor('support')
    const code = await screen.findByLabelText(/Support blueprint Python/i)
    expect(code.tagName).toBe('PRE')
    const desc = screen.getByText(/Viewing/i)
    expect(desc).toHaveTextContent('Viewing Support')
    expect(screen.getByText(/Bundled checkout recipe/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Save$/ })).toBeNull()
    expect(screen.queryByText(/Editing Support/i)).toBeNull()
  })
})
