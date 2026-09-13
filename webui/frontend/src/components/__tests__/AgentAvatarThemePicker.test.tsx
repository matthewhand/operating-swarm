import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AgentAvatar from '../AgentAvatar'
import AgentAvatarThemePicker from '../AgentAvatarThemePicker'
import AvatarThemePicker from '../AvatarThemePicker'
import AgentEditor from '../AgentEditor'
import { ToastProvider } from '../DaisyUI'
import { useAgentStore } from '../../lib/agent-store'
import {
  AVATAR_THEME_STORAGE_KEY,
  AVATAR_THEMES_ENABLED_KEY,
  saveEnabledAvatarThemes,
} from '../../lib/avatarTheme'

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

function stubFetch() {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo) => {
    const url = String(input)
    if (url.includes('/v1/image-gen/')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ object: 'image_gen', configured: false, status: 'off', avatars: {} }),
      } as Response
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ object: 'list', data: catalog }),
    } as Response
  }))
}

function renderEditor(agentId = 'codey') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AgentEditor isOpen={true} onClose={vi.fn()} agentId={agentId} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('AgentAvatarThemePicker (REQ-828)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.removeItem(AVATAR_THEME_STORAGE_KEY)
    localStorage.removeItem(AVATAR_THEMES_ENABLED_KEY)
    useAgentStore.setState({ avatarThemeByAgent: {}, avatarTheme: 'blobs' })
  })

  it('hides the theme combobox when only one theme is enabled', async () => {
    saveEnabledAvatarThemes(['blobs'])
    stubFetch()
    renderEditor()
    const dialog = await screen.findByRole('dialog', { name: /Edit /i, hidden: true })
    expect(within(dialog).queryByRole('combobox', { name: 'Theme' })).not.toBeInTheDocument()
  })

  it('lists enabled themes and lets agents mix looks', () => {
    saveEnabledAvatarThemes(['blobs', 'bee'])
    const { rerender } = render(<AgentAvatarThemePicker agentId="alpha" />)
    const picker = screen.getByLabelText(/theme/i)
    expect(picker).toBeInTheDocument()
    expect(within(picker).getByRole('option', { name: 'Bee' })).toBeInTheDocument()
    expect(within(picker).getByRole('option', { name: 'Blobs' })).toBeInTheDocument()
    fireEvent.change(picker, { target: { value: 'bee' } })
    expect(useAgentStore.getState().avatarThemeByAgent.alpha).toBe('bee')

    act(() => {
      saveEnabledAvatarThemes(['blobs'])
    })
    rerender(<AgentAvatarThemePicker agentId="alpha" />)
    expect(screen.queryByLabelText(/theme/i)).not.toBeInTheDocument()
  })

  it('shows the robot body suite when Robots is the only installed theme', () => {
    saveEnabledAvatarThemes(['robots'])
    render(<AgentAvatarThemePicker agentId="alpha" />)
    expect(screen.queryByRole('combobox', { name: 'Theme' })).not.toBeInTheDocument()
    const avatar = screen.getByRole('combobox', { name: 'Avatar' })
    expect(within(avatar).getByRole('option', { name: 'Chassis' })).toBeInTheDocument()
    expect(within(avatar).getByRole('option', { name: 'Crystal' })).toBeInTheDocument()
    fireEvent.change(avatar, { target: { value: 'pixel' } })
    expect(useAgentStore.getState().avatarThemeByAgent.alpha).toBe('pixel')
  })

  it('paints bee and blobs independently on two agents', () => {
    saveEnabledAvatarThemes(['blobs', 'bee'])
    useAgentStore.getState().setAgentAvatarTheme('alpha', 'bee')
    useAgentStore.getState().setAgentAvatarTheme('beta', 'blobs')
    const a = render(<AgentAvatar agentId="alpha" />)
    expect(a.container.querySelector('[data-avatar-theme]')).toHaveAttribute(
      'data-avatar-theme',
      'bee',
    )
    a.unmount()
    const b = render(<AgentAvatar agentId="beta" />)
    expect(b.container.querySelector('[data-avatar-theme]')).toHaveAttribute(
      'data-avatar-theme',
      'blobs',
    )
  })

  it('drops Bee from the agent picker after Settings disables it', () => {
    saveEnabledAvatarThemes(['blobs', 'bee'])
    const { rerender } = render(<AgentAvatarThemePicker agentId="alpha" />)
    expect(screen.getByRole('option', { name: 'Bee' })).toBeInTheDocument()
    act(() => {
      saveEnabledAvatarThemes(['blobs'])
    })
    rerender(<AgentAvatarThemePicker agentId="alpha" />)
    expect(screen.queryByRole('combobox', { name: 'Theme' })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Bee' })).not.toBeInTheDocument()
  })

  it('re-resolves mounted faces when Bee is unchecked (REQ-841)', () => {
    saveEnabledAvatarThemes(['blobs', 'bee'])
    useAgentStore.getState().setAgentAvatarTheme('alpha', 'bee')
    useAgentStore.getState().setAgentAvatarTheme('beta', 'blobs')
    const { container } = render(
      <>
        <AvatarThemePicker />
        <div data-testid="faces">
          <AgentAvatar agentId="alpha" />
          <AgentAvatar agentId="beta" />
        </div>
        <AgentAvatarThemePicker agentId="alpha" />
      </>,
    )
    const faces = screen.getByTestId('faces')
    expect(faces.querySelector('[data-avatar-theme="bee"]')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Bee' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('checkbox', { name: 'Bee' }))

    expect(useAgentStore.getState().avatarThemeByAgent.alpha).toBe('blobs')
    expect(useAgentStore.getState().avatarThemeByAgent.beta).toBe('blobs')
    expect(container.querySelector('[data-avatar-theme="bee"]')).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Bee' })).not.toBeInTheDocument()
  })

  it('omits a disabled theme from the click-avatar preview (REQ-841)', () => {
    saveEnabledAvatarThemes(['blobs', 'bee'])
    useAgentStore.getState().setAgentAvatarTheme('alpha', 'bee')
    render(
      <>
        <AvatarThemePicker />
        <AgentAvatar agentId="alpha" alt="Alpha" interactive />
      </>,
    )
    fireEvent.click(screen.getByRole('button', { name: /choose theme/i }))
    expect(
      within(screen.getByTestId('agent-theme-preview')).getByRole('tab', { name: 'Bee' }),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('checkbox', { name: 'Bee' }))

    expect(useAgentStore.getState().avatarThemeByAgent.alpha).toBe('blobs')
    fireEvent.click(screen.getByRole('button', { name: /choose theme/i }))
    const preview = screen.getByTestId('agent-theme-preview')
    expect(within(preview).queryByRole('tab', { name: 'Bee' })).not.toBeInTheDocument()
    expect(within(preview).getByRole('button', { name: 'Blobs' })).toBeInTheDocument()
  })
})

describe('AgentAvatar choose theme (REQ-840)', () => {
  afterEach(() => {
    localStorage.removeItem(AVATAR_THEME_STORAGE_KEY)
    localStorage.removeItem(AVATAR_THEMES_ENABLED_KEY)
    useAgentStore.setState({ avatarThemeByAgent: {}, avatarTheme: 'blobs' })
  })

  it('does not steal left-click when the face sits inside a rail link', () => {
    saveEnabledAvatarThemes(['blobs', 'bee'])
    const onNavigate = vi.fn()
    render(
      <a href="/chat?blueprint=alpha" onClick={(event) => {
        event.preventDefault()
        onNavigate()
      }}>
        <AgentAvatar agentId="alpha" alt="Alpha" />
      </a>,
    )
    expect(screen.queryByRole('button', { name: /choose theme/i })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('link'))
    expect(onNavigate).toHaveBeenCalledTimes(1)
    expect(screen.queryByTestId('agent-theme-preview')).not.toBeInTheDocument()
  })

  it('opens a preview of enabled themes when the avatar is clicked', () => {
    saveEnabledAvatarThemes(['blobs', 'bee'])
    render(<AgentAvatar agentId="alpha" alt="Alpha" interactive />)
    const trigger = screen.getByRole('button', { name: /choose theme/i })
    expect(trigger).toHaveAttribute('aria-haspopup', 'dialog')
    fireEvent.click(trigger)
    const preview = screen.getByTestId('agent-theme-preview')
    expect(preview).toBeInTheDocument()
    expect(within(preview).getByRole('tab', { name: 'Bee' })).toBeInTheDocument()
    expect(within(preview).getByRole('tab', { name: 'Blobs' })).toBeInTheDocument()
    fireEvent.click(within(preview).getByRole('tab', { name: 'Bee' }))
    expect(preview.querySelector('[data-avatar-theme="bee"]')).toBeInTheDocument()
    fireEvent.click(within(preview).getByRole('tab', { name: 'Blobs' }))
    expect(preview.querySelector('[data-avatar-theme="blobs"]')).toBeInTheDocument()
  })

  it('applies bee on A independently of blobs on B', () => {
    saveEnabledAvatarThemes(['blobs', 'bee'])
    const view = render(
      <>
        <AgentAvatar agentId="alpha" alt="Alpha" interactive />
        <AgentAvatar agentId="beta" alt="Beta" interactive />
      </>,
    )
    fireEvent.click(screen.getByRole('button', { name: /choose theme for alpha/i }))
    fireEvent.click(within(screen.getByTestId('agent-theme-preview')).getByRole('tab', { name: 'Bee' }))
    fireEvent.click(within(screen.getByTestId('agent-theme-preview')).getByRole('button', { name: 'Bee' }))
    expect(useAgentStore.getState().avatarThemeByAgent.alpha).toBe('bee')
    expect(screen.queryByTestId('agent-theme-preview')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /choose theme for beta/i }))
    fireEvent.click(within(screen.getByTestId('agent-theme-preview')).getByRole('tab', { name: 'Blobs' }))
    fireEvent.click(within(screen.getByTestId('agent-theme-preview')).getByRole('button', { name: 'Blobs' }))
    expect(useAgentStore.getState().avatarThemeByAgent.alpha).toBe('bee')
    expect(useAgentStore.getState().avatarThemeByAgent.beta).toBe('blobs')

    const alpha = screen.getByRole('button', { name: /choose theme for alpha/i })
    const beta = screen.getByRole('button', { name: /choose theme for beta/i })
    expect(alpha.querySelector('[data-avatar-theme]') || alpha).toHaveAttribute(
      'data-avatar-theme',
      'bee',
    )
    expect(beta.querySelector('[data-avatar-theme]') || beta).toHaveAttribute(
      'data-avatar-theme',
      'blobs',
    )
    view.unmount()
  })

  it('still opens the popup when only one theme is enabled', () => {
    saveEnabledAvatarThemes(['bee'])
    render(<AgentAvatar agentId="alpha" alt="Alpha" interactive />)
    fireEvent.click(screen.getByRole('button', { name: /choose theme/i }))
    const preview = screen.getByTestId('agent-theme-preview')
    expect(within(preview).getByRole('button', { name: 'Bee' })).toBeInTheDocument()
    expect(preview.querySelector('[data-avatar-theme="bee"]')).toBeInTheDocument()
    expect(within(preview).queryByRole('button', { name: 'Blobs' })).not.toBeInTheDocument()
  })

  it('does not prevent the rail context menu on right-click', () => {
    render(<AgentAvatar agentId="alpha" alt="Alpha" interactive />)
    const trigger = screen.getByRole('button', { name: /choose theme/i })
    const event = fireEvent.contextMenu(trigger)
    expect(event).toBe(true)
  })

  it('keeps a custom upload on the live face after choosing bee', () => {
    saveEnabledAvatarThemes(['blobs', 'bee'])
    render(
      <AgentAvatar agentId="alpha" alt="Alpha" src="/avatars/uploaded.png" interactive />,
    )
    fireEvent.click(screen.getByRole('button', { name: /choose theme/i }))
    const preview = screen.getByTestId('agent-theme-preview')
    fireEvent.click(within(preview).getByRole('tab', { name: 'Bee' }))
    fireEvent.click(within(preview).getByRole('button', { name: 'Bee' }))
    expect(useAgentStore.getState().avatarThemeByAgent.alpha).toBe('bee')
    expect(screen.getByRole('button', { name: /choose theme/i }).querySelector('img')).toHaveAttribute(
      'src',
      '/avatars/uploaded.png',
    )
  })
})
