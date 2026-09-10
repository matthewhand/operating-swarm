import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ToastProvider } from '../DaisyUI'
import CliSessionSwitcher from '../CliSessionSwitcher'
import * as cliSessions from '../../lib/cliSessions'
import * as cliSessionHop from '../../lib/cliSessionHop'
import * as api from '../../lib/api'
import type { CliSessionList } from '../../lib/cliSessions'

function listPayload(title: string, id = 'sid-1'): CliSessionList {
  return {
    object: 'cli_session_list',
    agent_id: 'cli_agent',
    cli: 'grok',
    can_list: true,
    sessions: [
      {
        id,
        title,
        snippet: 'alpha work',
        updated_at: '2026-09-05T12:00:00Z',
        source: 'provider',
      },
    ],
    recent: [],
    empty_reason: null,
    activity_sot: 'provider',
  }
}

function renderSwitcher() {
  return render(
    <MemoryRouter>
      <ToastProvider>
        <CliSessionSwitcher agentId="cli_agent" cli="grok" agentName="cli_agent" />
      </ToastProvider>
    </MemoryRouter>,
  )
}

describe('CliSessionSwitcher', () => {
  beforeEach(() => {
    vi.spyOn(cliSessions, 'fetchCliSessions').mockResolvedValue({
      object: 'cli_session_list',
      agent_id: 'cli_agent',
      cli: 'grok',
      can_list: true,
      sessions: [
        {
          id: 'sid-1',
          title: 'First',
          snippet: 'alpha work',
          updated_at: '2026-09-05T12:00:00Z',
          source: 'provider',
        },
      ],
      recent: [],
      empty_reason: null,
      activity_sot: 'provider',
    })
    vi.spyOn(api, 'fetchCliAgents').mockResolvedValue({
      clis: ['grok', 'claude'],
      native_consensus: {},
      catalog: {},
    })
    vi.spyOn(cliSessions, 'selectCliSession').mockResolvedValue({
      object: 'cli_session_select',
      agent_id: 'cli_agent',
      cli: 'grok',
      conversation_id: 'conv-9',
      cli_session_id: 'sid-1',
      messages: [],
      status: 'ok',
      collapsed_prior: false,
      import: 'none',
    })
    vi.spyOn(cliSessions, 'dispatchCliSessionSwitched').mockImplementation(() => {})
    vi.spyOn(cliSessionHop, 'dispatchCliSessionHopped').mockImplementation(() => {})
    vi.spyOn(cliSessionHop, 'hopCliSession').mockResolvedValue({
      object: 'cli_session_hop',
      agent_id: 'cli_agent',
      conversation_id: 'conv-hop',
      from_cli: 'grok',
      to_cli: 'claude',
      kind: 'cli',
      cli_session_id: null,
      mode: 'summary',
      tokens: 12,
      token_budget: 800,
      omitted: [],
      empty: false,
      status: 'Carried summary context from grok → claude (12 tokens).',
      export_warning: null,
      import: 'transcript',
      injection: { text: '', mode: 'summary', tokens: 12, empty: false },
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('does not list sessions until the navbar control is opened', () => {
    renderSwitcher()
    expect(screen.getByTestId('os-cli-session-switcher')).toBeInTheDocument()
    expect(screen.queryByTestId('os-cli-session-picker')).not.toBeInTheDocument()
    expect(cliSessions.fetchCliSessions).not.toHaveBeenCalled()
  })

  it('opens the picker and binds a selected session (REQ-104)', async () => {
    renderSwitcher()
    fireEvent.click(screen.getByRole('button', { name: 'Select cli_agent session' }))
    const picker = await screen.findByTestId('os-cli-session-picker')
    expect(picker).toBeInTheDocument()
    await waitFor(() => {
      expect(cliSessions.fetchCliSessions).toHaveBeenCalledWith('cli_agent', 'grok')
    })
    fireEvent.click(screen.getByRole('option', { name: /First/ }))
    await waitFor(() => {
      expect(cliSessions.selectCliSession).toHaveBeenCalledWith(
        expect.objectContaining({
          agentId: 'cli_agent',
          cli: 'grok',
          sessionId: 'sid-1',
        }),
      )
    })
    expect(cliSessions.dispatchCliSessionSwitched).toHaveBeenCalledWith({
      agentId: 'cli_agent',
      conversationId: 'conv-9',
      status: 'ok',
    })
  })

  it('starts a new session from the picker footer', async () => {
    renderSwitcher()
    fireEvent.click(screen.getByRole('button', { name: 'Select cli_agent session' }))
    await screen.findByTestId('os-cli-session-picker')
    fireEvent.click(screen.getByTestId('cli-session-start-new'))
    await waitFor(() => {
      expect(cliSessions.selectCliSession).toHaveBeenCalledWith(
        expect.objectContaining({
          agentId: 'cli_agent',
          cli: 'grok',
          startNew: true,
        }),
      )
    })
  })

  it('ignores a stale list response after a newer open', async () => {
    const resolvers: Array<(value: CliSessionList) => void> = []
    vi.mocked(cliSessions.fetchCliSessions).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvers.push(resolve)
        }),
    )
    renderSwitcher()
    fireEvent.click(screen.getByRole('button', { name: 'Select cli_agent session' }))
    fireEvent.click(screen.getByRole('button', { name: 'Select cli_agent session' }))
    await waitFor(() => expect(resolvers).toHaveLength(2))
    resolvers[0](listPayload('Stale', 'sid-stale'))
    await Promise.resolve()
    expect(screen.queryByRole('option', { name: /Stale/ })).not.toBeInTheDocument()
    resolvers[1](listPayload('Fresh', 'sid-fresh'))
    expect(await screen.findByRole('option', { name: /Fresh/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Stale/ })).not.toBeInTheDocument()
  })

  it('continues on another CLI without writing hop status onto the source thread', async () => {
    renderSwitcher()
    fireEvent.click(screen.getByRole('button', { name: 'Select cli_agent session' }))
    await screen.findByRole('option', { name: /First/ })
    fireEvent.change(screen.getByTestId('cli-session-continue-on'), { target: { value: 'claude' } })
    await waitFor(() => {
      expect(cliSessionHop.hopCliSession).toHaveBeenCalledWith(
        expect.objectContaining({
          agentId: 'cli_agent',
          fromCli: 'grok',
          toCli: 'claude',
          importSessionId: 'sid-1',
        }),
      )
    })
    expect(cliSessionHop.dispatchCliSessionHopped).not.toHaveBeenCalled()
    expect(await screen.findByText('Session continued')).toBeInTheDocument()
  })
})
