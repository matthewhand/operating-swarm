import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ChatMessageList } from '../ChatMessageList'
import {
  OPENAI_AGENTS_TIP_STORAGE_KEY,
  TEAM_BLUEPRINT_TIP_STORAGE_KEY,
} from '../../../lib/blueprintTips'
import { __resetUserPrefsCacheForTests } from '../../../lib/userPrefs'

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response
}

function stubFetch() {
  const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/v1/preferences/')) {
      return jsonResponse({
        object: 'user_preferences',
        principal: 'session:test',
        guest: true,
        empty: true,
        favourites: [],
        hidden_agents: [],
        hostname_override: '',
        values: {},
      })
    }
    return jsonResponse({ object: 'list', data: [] })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function renderList(over: Record<string, unknown> = {}) {
  return render(
    <ChatMessageList displayItems={[]} messages={[]} threadReady={false} {...over} />,
  )
}

describe('#1252 chat blueprint tip integration', () => {
  beforeEach(() => {
    localStorage.clear()
    __resetUserPrefsCacheForTests()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
    __resetUserPrefsCacheForTests()
  })

  it('shows the workspace-team tip first time a team seat is used', async () => {
    stubFetch()
    renderList({ teamFromUrl: 'office', selectedAgentName: 'Office' })
    expect(await screen.findByTestId('team-blueprint-tip')).toBeInTheDocument()
    expect(screen.getByTestId('chat-messages-container')).toBeInTheDocument()
  })

  it('plain dismiss hides the tip for this mount without persisting', async () => {
    stubFetch()
    renderList({ teamFromUrl: 'office' })
    fireEvent.click(await screen.findByTestId('team-blueprint-tip-dismiss'))
    await waitFor(() => {
      expect(screen.queryByTestId('team-blueprint-tip')).not.toBeInTheDocument()
    })
    expect(localStorage.getItem(TEAM_BLUEPRINT_TIP_STORAGE_KEY)).toBeNull()
    expect(screen.getByTestId('chat-messages-container')).toBeInTheDocument()
  })

  it('never-show-again persists and is respected across remounts', async () => {
    const fetchMock = stubFetch()
    const first = renderList({ teamFromUrl: 'office' })
    fireEvent.click(await screen.findByTestId('team-blueprint-tip-never'))
    fireEvent.click(screen.getByTestId('team-blueprint-tip-dismiss'))
    await waitFor(() => {
      expect(screen.queryByTestId('team-blueprint-tip')).not.toBeInTheDocument()
    })
    expect(localStorage.getItem(TEAM_BLUEPRINT_TIP_STORAGE_KEY)).toBe('1')
    const patch = fetchMock.mock.calls.find(
      (call) =>
        String(call[0]).includes('/v1/preferences/') &&
        (call[1] as RequestInit | undefined)?.method === 'PATCH',
    )
    expect(patch).toBeTruthy()

    first.unmount()
    __resetUserPrefsCacheForTests()
    renderList({ teamFromUrl: 'office' })
    await waitFor(() => {
      expect(screen.queryByTestId('team-blueprint-tip')).not.toBeInTheDocument()
    })
  })

  it('gates the openai-agents tip behind the experimental flag (#1230)', async () => {
    stubFetch()
    const first = renderList({ selectedBlueprint: { id: 'openai-agents' } })
    expect(screen.queryByTestId('openai-agents-tip')).not.toBeInTheDocument()
    first.unmount()

    localStorage.setItem('swarm_experimental_openai_agents', 'on')
    __resetUserPrefsCacheForTests()
    stubFetch()
    renderList({ selectedBlueprint: { id: 'openai-agents' } })
    expect(await screen.findByTestId('openai-agents-tip')).toBeInTheDocument()
    // The dismissed key is independent from the team key.
    expect(localStorage.getItem(OPENAI_AGENTS_TIP_STORAGE_KEY)).toBeNull()
  })
})
