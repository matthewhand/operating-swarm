import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MarketplaceScanSection } from '../MarketplaceScanSection'

const SCAN_OK = {
  object: 'marketplace_scan',
  kind: 'plugins',
  topics: ['swarm-mcp-plugin', 'open-swarm-plugin'],
  external: true,
  items: [
    {
      id: 'alice/cool-mcp',
      name: 'cool-mcp',
      full_name: 'alice/cool-mcp',
      owner: 'alice',
      description: 'A cool MCP plugin',
      html_url: 'https://github.com/alice/cool-mcp',
      stars: 42,
      topics: ['swarm-mcp-plugin'],
      updated_at: '2026-09-01T00:00:00Z',
    },
  ],
  warnings: [],
}

function renderSection(kind: 'teams' | 'plugins' = 'plugins') {
  return render(<MarketplaceScanSection kind={kind} />)
}

describe('MarketplaceScanSection (#179)', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('scans the right endpoint on expand and labels results as external', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => SCAN_OK,
    } as Response)
    vi.stubGlobal('fetch', fetchMock)

    renderSection('plugins')
    const toggle = screen.getByTestId('marketplace-toggle')
    expect(toggle).toHaveTextContent('Get more from GitHub')
    expect(screen.queryByTestId('marketplace-results')).toBeNull()

    fireEvent.click(toggle)
    await waitFor(() => {
      expect(screen.getByTestId('marketplace-item')).toBeInTheDocument()
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/v1/marketplace/?kind=plugins',
      expect.anything(),
    )
    expect(screen.getByRole('link', { name: /alice\/cool-mcp/ })).toHaveAttribute(
      'href',
      'https://github.com/alice/cool-mcp',
    )
    expect(
      screen.getByText(/Community \/ external content/i),
    ).toBeInTheDocument()
  })

  it('passes kind=teams for the Teams popup variant', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ...SCAN_OK, kind: 'teams', items: [] }),
    } as Response)
    vi.stubGlobal('fetch', fetchMock)

    renderSection('teams')
    fireEvent.click(screen.getByTestId('marketplace-toggle'))
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/v1/marketplace/?kind=teams',
        expect.anything(),
      )
    })
    expect(screen.getByText(/Nothing found/i)).toBeInTheDocument()
  })

  it('shows honest warnings (rate limit) instead of fake results', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          ...SCAN_OK,
          items: [],
          warnings: ['GitHub rate limit reached — try again later or set GITHUB_TOKEN.'],
        }),
      } as Response),
    )

    renderSection()
    fireEvent.click(screen.getByTestId('marketplace-toggle'))
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(/rate limit/i)
    })
    expect(screen.queryByTestId('marketplace-item')).toBeNull()
  })

  it('shows an error message when the backend scan fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('Scan failed.')),
    )

    renderSection()
    fireEvent.click(screen.getByTestId('marketplace-toggle'))
    await waitFor(() => {
      expect(screen.getByText('Scan failed.')).toBeInTheDocument()
    })
  })
})
