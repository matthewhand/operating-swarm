import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { LibraryScopeProof1311, LIBRARY_SCOPE_PROOF_1311_PATH } from '../LibraryScopeProof1311'

describe('library scope proof route (#1311)', () => {
  it('stamps the proof path and mounts Mine / Team / Organisation', async () => {
    window.history.pushState({}, '', `${LIBRARY_SCOPE_PROOF_1311_PATH}?step=mine`)
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: [] }),
      })),
    )
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <LibraryScopeProof1311 />
      </QueryClientProvider>,
    )
    expect(screen.getByTestId('proof-url-1311').textContent).toContain(LIBRARY_SCOPE_PROOF_1311_PATH)
    expect(screen.getByTestId('proof-url-1311').textContent).toContain('step=mine')
    expect(screen.getByRole('button', { name: 'Mine' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Team' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Organisation' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add Support to rail' })).toBeInTheDocument()
    vi.unstubAllGlobals()
  })
})
