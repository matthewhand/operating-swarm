/**
 * #907 — TechSupportModal: fetch GET /v1/diagnostics/ (#905) and render the
 * sanitized bundle for inspection and copy.
 *
 * Security stance: the payload is masked server-side (#904); the modal does
 * not un-mask and additionally redacts secret-shaped keys client-side, so a
 * malformed/poisoned payload cannot leak raw env-style values.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import TechSupportModal from '../TechSupportModal'
import { apiGet } from '../../lib/api'

vi.mock('../../lib/api', () => ({
  apiGet: vi.fn(),
}))

const PAYLOAD = {
  recent_logs: {
    lines: [
      { ts: '2026-09-21T10:00:00', level: 'INFO', logger: 'swarm.a', message: 'started ok' },
      { ts: '2026-09-21T10:00:01', level: 'ERROR', logger: 'swarm.b', message: 'boom happened' },
      { ts: '2026-09-21T10:00:02', level: 'WARNING', logger: 'swarm.c', message: 'slow turn' },
    ],
    counts: { DEBUG: 0, INFO: 1, WARNING: 1, ERROR: 1, CRITICAL: 0, OTHER: 0 },
    unavailable: false,
  },
  config_dump: {
    remotes: { hermes: { url: 'http://example.internal', agents: 2 } },
    llm_profiles: { default: 'grok-4' },
    routing_models: { compact: 'mini' },
    config_path: '/home/me/.swarm/config.yaml',
    not_a_secret_value: 'plain',
    api_key: 'sk-ant-should-not-render',
    db_password: 'hunter2',
  },
  server_facts: {
    app_version: '9.9.9',
    local_store: { path: '/home/me/.swarm/db.sqlite', size_label: '1.2 MB' },
    log_levels: { django: 'INFO', swarm: 'DEBUG' },
  },
}

describe('#907 TechSupportModal', () => {
  beforeEach(() => {
    vi.mocked(apiGet).mockResolvedValue(PAYLOAD)
  })

  afterEach(() => {
    vi.mocked(apiGet).mockReset()
  })

  it('fetches the diagnostics endpoint on open and renders the three sections', async () => {
    render(<TechSupportModal open onClose={vi.fn()} />)
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/v1/diagnostics/'))
    expect(await screen.findByTestId('tech-support-modal')).toBeInTheDocument()
    expect(screen.getByTestId('tech-support-logs')).toHaveTextContent('boom happened')
    expect(screen.getByTestId('tech-support-config')).toHaveTextContent('grok-4')
    expect(screen.getByTestId('tech-support-facts')).toHaveTextContent('9.9.9')
  })

  it('shows a loading state while the request is in flight', async () => {
    let resolveFetch: (v: unknown) => void = () => {}
    vi.mocked(apiGet).mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve
      }) as never,
    )
    render(<TechSupportModal open onClose={vi.fn()} />)
    expect(screen.getByTestId('tech-support-loading')).toBeInTheDocument()
    resolveFetch(PAYLOAD)
    expect(await screen.findByTestId('tech-support-modal')).toBeInTheDocument()
  })

  it('shows an error state when the fetch fails', async () => {
    vi.mocked(apiGet).mockRejectedValue(new Error('network down'))
    render(<TechSupportModal open onClose={vi.fn()} />)
    expect(await screen.findByTestId('tech-support-error')).toHaveTextContent(/network down/i)
  })

  it('redacts secret-shaped keys even from a malformed server payload', async () => {
    render(<TechSupportModal open onClose={vi.fn()} />)
    await screen.findByTestId('tech-support-modal')
    expect(screen.queryByText(/sk-ant-should-not-render/)).toBeNull()
    expect(screen.queryByText(/hunter2/)).toBeNull()
    expect(screen.getByText('plain')).toBeInTheDocument()
  })

  it('narrows the log lines with the level filter', async () => {
    render(<TechSupportModal open onClose={vi.fn()} />)
    await screen.findByTestId('tech-support-modal')
    fireEvent.click(screen.getByRole('button', { name: /error \(1\)/i }))
    expect(screen.getByTestId('tech-support-logs')).toHaveTextContent('boom happened')
    expect(screen.getByTestId('tech-support-logs')).not.toHaveTextContent('started ok')
  })

  it('copies the redacted payload and confirms', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    render(<TechSupportModal open onClose={vi.fn()} />)
    await screen.findByTestId('tech-support-modal')
    fireEvent.click(screen.getByRole('button', { name: /copy diagnostics/i }))
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1))
    const copied = JSON.stringify(writeText.mock.calls[0][0])
    // What lands on the clipboard is exactly what the modal shows: masked.
    expect(copied).not.toContain('sk-ant-should-not-render')
    expect(copied).not.toContain('hunter2')
    expect(copied).toContain('plain')
    expect(screen.getByTestId('tech-support-copied')).toBeInTheDocument()
  })

  it('close button and Escape both close the modal', async () => {
    const onClose = vi.fn()
    render(<TechSupportModal open onClose={onClose} />)
    await screen.findByTestId('tech-support-modal')
    fireEvent.click(screen.getByRole('button', { name: /close diagnostics/i }))
    expect(onClose).toHaveBeenCalledTimes(1)
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})
