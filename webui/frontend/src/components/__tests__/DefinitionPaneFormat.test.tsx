/**
 * #537 — the Definition source editor fills the pane and offers Format.
 *
 * - The textarea carries `w-full` so it is not pinned to DaisyUI's 20rem
 *   `.textarea` width clamp.
 * - A `Format` control is offered for `.py` files only; it posts the draft
 *   to /source/format and fills the editor with the proposal — saving
 *   stays an explicit user action.
 * - Non-Python files (README.md) never offer the control.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DefinitionPane from '../DefinitionPane'
import { ToastProvider } from '../DaisyUI'

function renderPane(kind: 'role' | 'blueprint' | 'team' = 'role', id = 'support') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <DefinitionPane kind={kind} definitionId={id} />
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

function stubSource(overrides: Record<string, unknown>) {
  return vi.fn().mockImplementation(async (input: RequestInfo) => {
    const url = String(input)
    if (url.includes('/source/format')) {
      return jsonResponse({ formatted: 'FORMATTED_SOURCE' })
    }
    if (url.includes('/source')) {
      return jsonResponse({
        id: 'user_recipe',
        files: [{ name: 'blueprint_user_recipe.py', path: 'blueprint_user_recipe.py' }],
        primary: 'blueprint_user_recipe.py',
        selected: 'blueprint_user_recipe.py',
        content: 'ORIGINAL_SOURCE',
        editable: true,
        origin: 'user',
        readonly_reason: null,
        ...overrides,
      })
    }
    return jsonResponse({
      kind: 'role',
      id: 'user_recipe',
      title: 'User Recipe',
      role: 'support',
      explanation: 'Explanation.',
      source: 'ORIGINAL_SOURCE',
      injected: { system_prompt: '', tools: {}, metadata: {}, handoff: '', extra: '' },
      default_llm: { configured: false, model: null },
    })
  })
}

describe('#537: Definition editor width + Format', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('textarea renders full width (w-full), not the 20rem DaisyUI clamp', async () => {
    vi.stubGlobal('fetch', stubSource({}))
    renderPane('role', 'user_recipe')
    fireEvent.click(await screen.findByRole('button', { name: /edit code/i }))
    const editor = screen.getByLabelText('Definition source')
    expect(editor).toHaveClass('w-full')
    expect(editor).toHaveClass('min-h-56')
  })

  it('offers Format for a .py file and fills the draft with the proposal', async () => {
    const fetchMock = stubSource({})
    vi.stubGlobal('fetch', fetchMock)
    renderPane('role', 'user_recipe')
    fireEvent.click(await screen.findByRole('button', { name: /edit code/i }))
    const editor = screen.getByLabelText('Definition source')

    fireEvent.click(await screen.findByTestId('definition-format'))
    await waitFor(() => {
      expect(screen.getByTestId('definition-format-hint')).toHaveTextContent(
        /Formatted — review, then Save/i,
      )
    })
    expect((editor as HTMLTextAreaElement).value).toBe('FORMATTED_SOURCE')

    const formatPost = fetchMock.mock.calls.find(([input]) =>
      String(input).includes('/source/format'),
    )
    expect(formatPost).toBeTruthy()
  })

  it('hides Format for non-Python files', async () => {
    vi.stubGlobal(
      'fetch',
      stubSource({
        selected: 'README.md',
        files: [
          { name: 'blueprint_user_recipe.py', path: 'blueprint_user_recipe.py' },
          { name: 'README.md', path: 'README.md' },
        ],
      }),
    )
    renderPane('role', 'user_recipe')
    fireEvent.click(await screen.findByRole('button', { name: /edit code/i }))
    expect(screen.queryByTestId('definition-format')).not.toBeInTheDocument()
  })

  it('shows the error message when the formatter is unavailable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/source/format')) {
          return jsonResponse(
            { error: 'No Python formatter is available on this host (install ruff or black).' },
            501,
          )
        }
        if (url.includes('/source')) {
          return jsonResponse({
            id: 'user_recipe',
            files: [{ name: 'blueprint_user_recipe.py', path: 'blueprint_user_recipe.py' }],
            primary: 'blueprint_user_recipe.py',
            selected: 'blueprint_user_recipe.py',
            content: 'ORIGINAL_SOURCE',
            editable: true,
            origin: 'user',
            readonly_reason: null,
          })
        }
        return jsonResponse({
          kind: 'role',
          id: 'user_recipe',
          title: 'User Recipe',
          role: 'support',
          explanation: 'Explanation.',
          source: 'ORIGINAL_SOURCE',
          injected: { system_prompt: '', tools: {}, metadata: {}, handoff: '', extra: '' },
          default_llm: { configured: false, model: null },
        })
      }),
    )
    renderPane('role', 'user_recipe')
    fireEvent.click(await screen.findByRole('button', { name: /edit code/i }))
    fireEvent.click(screen.getByTestId('definition-format'))
    await waitFor(() => {
      expect(screen.getByTestId('definition-format-hint')).toHaveTextContent(
        /No Python formatter is available/i,
      )
    })
  })
})
