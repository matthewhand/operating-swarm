import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AgentEditor from '../AgentEditor'
import AgentAvatar from '../AgentAvatar'
import { ChatHeader } from '../../features/chat/ChatHeader'
import { ToastProvider } from '../DaisyUI'
import { AGENT_EDITS_KEY, editedAgentLabel } from '../../lib/agentEdits'
import {
  AGENT_PROFILE_CHANGED_EVENT,
  peekAgentProfile,
  resetAgentProfileCache,
} from '../../lib/agentProfile'

const catalog = [
  {
    id: 'codey',
    object: 'blueprint' as const,
    name: 'Codey',
    description: 'Code assistant',
    abbreviation: null,
    required_mcp_servers: [] as string[],
    tags: [] as string[],
    installed: true,
    compiled: true,
  },
]

const emptyProfile = {
  object: 'agent_profile',
  agent_id: 'codey',
  display_name: '',
  description: '',
  title: '',
  role: '',
  avatar_shape: 'circle',
  avatar_color: '',
  avatar_path: null,
  profile: {
    display_name: '',
    description: '',
    title: '',
    role: '',
    avatar_shape: 'circle',
    avatar_color: '',
    avatar_path: null,
  },
  pack: {
    schema: 1,
    kind: 'agent_template',
    agent_id: 'codey',
    profile: {
      display_name: '',
      description: '',
      title: '',
      role: '',
      avatar_shape: 'circle',
      avatar_color: '',
      avatar_path: null,
    },
  },
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

function stubApis(profileStore: { current: Record<string, unknown> }) {
  const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = (init?.method || 'GET').toUpperCase()
    if (url.includes('/v1/agents/') && url.includes('/profile/')) {
      const idMatch = url.match(/\/v1\/agents\/([^/]+)\/profile/)
      const agentId = decodeURIComponent(idMatch?.[1] || 'codey')
      if (method === 'GET') {
        return jsonResponse(profileStore.current[agentId] || { ...emptyProfile, agent_id: agentId })
      }
      const patch = init?.body ? JSON.parse(String(init.body)) : {}
      const prev = (profileStore.current[agentId] || emptyProfile) as typeof emptyProfile
      const nextProfile = {
        ...prev.profile,
        ...patch,
        ...(patch.profile || {}),
      }
      const next = {
        ...emptyProfile,
        agent_id: agentId,
        ...nextProfile,
        profile: nextProfile,
        pack: {
          schema: 1,
          kind: 'agent_template',
          agent_id: agentId,
          profile: nextProfile,
        },
      }
      profileStore.current[agentId] = next
      return jsonResponse(next)
    }
    if (url.includes('/v1/agents/') && url.includes('/settings/')) {
      return jsonResponse({
        object: 'agent_settings',
        agent_id: 'codey',
        new_chat_per_task: false,
        use_suggestions: false,
        ...(emptyProfile.profile),
        profile: emptyProfile.profile,
      })
    }
    if (url.includes('/v1/skills')) {
      return jsonResponse({ object: 'list', data: [] })
    }
    if (url.includes('/v1/models')) {
      return jsonResponse({
        object: 'list',
        data: [{ id: 'default', object: 'model', created: 0, owned_by: 'swarm' }],
      })
    }
    return jsonResponse({ object: 'list', data: catalog })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function RailHeaderChrome({ agentId }: { agentId: string }) {
  const [tick, setTick] = useState(0)
  useEffect(() => {
    const onChange = () => setTick((value) => value + 1)
    window.addEventListener(AGENT_PROFILE_CHANGED_EVENT, onChange)
    window.addEventListener('swarm:agent-edits-changed', onChange)
    return () => {
      window.removeEventListener(AGENT_PROFILE_CHANGED_EVENT, onChange)
      window.removeEventListener('swarm:agent-edits-changed', onChange)
    }
  }, [])
  const name = editedAgentLabel({ id: agentId, name: 'Codey' })
  const profile = peekAgentProfile(agentId)
  void tick
  return (
    <div>
      <div data-testid="rail-chrome">
        <span data-testid="rail-agent-name">{name}</span>
        <span data-testid="rail-agent-description">{profile?.description || ''}</span>
        <AgentAvatar agentId={agentId} />
      </div>
      <ChatHeader
        AgentAvatar={AgentAvatar}
        ApiSessionSwitcher={() => null}
        AuxActivityIndicator={() => null}
        CliSessionSwitcher={() => null}
        ComputerControlStub={() => null}
        OPEN_SETTINGS_EVENT="swarm:open-settings"
        RemoteSessionSwitcher={() => null}
        Settings={() => <span />}
        Pencil={() => <span />}
        Folder={() => <span />}
        PanelLeft={() => <span />}
        roleCssClass={() => ''}
        ThemeToggle={() => <span />}
        selectedAgentName={name}
        selectedAgent={{ id: agentId, name }}
        selectedBlueprint={agentId}
        headerFaceAgentId={agentId}
        activeChatAgentId={agentId}
        auxTasks={[]}
        requestAuxCancel={() => undefined}
        wsRef={{ current: null }}
        showEmptyRemoteChrome={false}
        showRemotesControl={false}
        activeRemoteId={null}
        configuredRemoteRows={[]}
        selectedRemote={null}
        setSearchParams={() => undefined}
        setGenerationsOpen={() => undefined}
        generationsOpen={false}
        cliRemoteSession={null}
        openAgentEditor={() => undefined}
        openSettingsSheet={() => undefined}
        openTeamEditor={() => undefined}
        openRail={() => undefined}
        railOpen
        navigateToPaletteAgent={() => undefined}
        allPaletteAgents={[]}
      />
    </div>
  )
}

function renderEditor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <RailHeaderChrome agentId="codey" />
        <AgentEditor isOpen onClose={() => undefined} agentId="codey" />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('AgentEditor storefront profile (#1389)', () => {
  const profileStore = { current: {} as Record<string, unknown> }

  afterEach(() => {
    localStorage.removeItem(AGENT_EDITS_KEY)
    resetAgentProfileCache()
    profileStore.current = {}
    vi.unstubAllGlobals()
  })

  it('saves name, description, title, avatar shape/color and updates rail + header without reload', async () => {
    const fetchMock = stubApis(profileStore)
    renderEditor()

    const dialog = await screen.findByRole('dialog', { name: /Edit /i, hidden: true })
    const identity = within(dialog).getByRole('tabpanel', { name: /Identity/i })
    // #1677: the three profile strings are click-to-edit now. Drive them the
    // way a user does — click, type, commit — and keep every assertion below
    // exactly as it was: same PATCH bodies, same rail/header propagation.
    const nameTrigger = within(identity).getByTestId('agent-field-name-trigger')
    await waitFor(() => expect(nameTrigger).toHaveTextContent('Codey'))
    fireEvent.click(nameTrigger)
    const nameInput = within(identity).getByLabelText('Name')
    fireEvent.change(nameInput, { target: { value: 'Honey Bee' } })
    fireEvent.keyDown(nameInput, { key: 'Enter' })

    fireEvent.click(within(identity).getByTestId('agent-field-description-trigger'))
    const descriptionInput = within(identity).getByLabelText('Description')
    fireEvent.change(descriptionInput, { target: { value: 'Short storefront blurb' } })
    fireEvent.blur(descriptionInput)

    fireEvent.click(within(identity).getByTestId('agent-field-title-trigger'))
    const titleInput = within(identity).getByLabelText('Title')
    fireEvent.change(titleInput, { target: { value: 'Guide' } })
    fireEvent.keyDown(titleInput, { key: 'Enter' })

    fireEvent.change(within(identity).getByLabelText('Avatar shape'), {
      target: { value: 'hexagon' },
    })
    fireEvent.change(within(identity).getByLabelText('Avatar color'), {
      target: { value: '#f59e0b' },
    })

    await waitFor(() => {
      const patches = fetchMock.mock.calls.filter(([url, init]) => {
        return String(url).includes('/profile/') && String(init?.method || '').toUpperCase() === 'PATCH'
      })
      expect(patches.length).toBeGreaterThan(0)
    })

    await waitFor(() => {
      expect(screen.getByTestId('rail-agent-name')).toHaveTextContent('Honey Bee')
      expect(screen.getByTestId('rail-agent-description')).toHaveTextContent('Short storefront blurb')
      expect(screen.getByTestId('os-identity-name')).toHaveTextContent('Honey Bee')
      expect(screen.getByTestId('os-header-profile-title')).toHaveTextContent('Guide')
    })

    const chromeAvatar = screen.getByTestId('rail-chrome').querySelector('[data-avatar-shape]')
    expect(chromeAvatar).toHaveAttribute('data-avatar-shape', 'hexagon')
    expect(chromeAvatar).toHaveAttribute('data-avatar-color', '#f59e0b')

    const bodies = fetchMock.mock.calls
      .filter(([url, init]) => {
        return String(url).includes('/profile/') && String(init?.method || '').toUpperCase() === 'PATCH'
      })
      .map(([, init]) => JSON.parse(String((init as RequestInit).body || '{}')))
    expect(bodies.some((body) => body.display_name === 'Honey Bee')).toBe(true)
    expect(bodies.some((body) => body.description === 'Short storefront blurb')).toBe(true)
    expect(bodies.some((body) => body.title === 'Guide')).toBe(true)
    expect(bodies.some((body) => body.avatar_shape === 'hexagon')).toBe(true)
    expect(bodies.some((body) => body.avatar_color === '#f59e0b')).toBe(true)
    const dumped = JSON.stringify(bodies)
    expect(dumped).not.toContain('sk-')
    expect(dumped).not.toContain('api_key')
  })
})
