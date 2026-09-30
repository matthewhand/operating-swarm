import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TemplatesGallery from '../TemplatesGallery'
import { SHIPPED_STOREFRONT_BEE, SHIPPED_SWARM_ENGINEER } from '../../lib/agentTemplates'
import { publishCurrentAgent } from '../../lib/currentAgent'
import { ToastProvider } from '../DaisyUI'

const GROK = {
  object: 'grok_bot_template',
  schema: 1,
  kind: 'grok_bot_template',
  name: 'Storefront Bee',
  description: 'Short storefront blurb for the rail and pack card.',
  title: 'Guide',
  role: 'support',
  avatar: { shape: 'hexagon', color: '#f59e0b', path: '/avatars/bee/bee-profile-worker.svg' },
  memories: SHIPPED_STOREFRONT_BEE.memories,
  skills: SHIPPED_STOREFRONT_BEE.skills,
  gettingStarted: SHIPPED_STOREFRONT_BEE.gettingStarted,
  routines: [],
  plugins: [],
}

function jsonOk(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function jsonErr(status: number, error: string, code?: string): Response {
  return new Response(JSON.stringify({ error, code }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderGallery(open = true) {
  const onClose = vi.fn()
  render(
    <ToastProvider>
      <TemplatesGallery open={open} onClose={onClose} />
    </ToastProvider>,
  )
  return { onClose }
}

describe('#1399 TemplatesGallery', () => {
  beforeEach(() => {
    localStorage.clear()
    publishCurrentAgent({ id: 'codey', kind: 'api' })
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        const method = init?.method || 'GET'
        if (url === '/v1/agents/codey/template/' && method === 'GET') {
          return jsonOk({ ...SHIPPED_STOREFRONT_BEE, object: 'agent_template' })
        }
        if (url === '/v1/agents/codey/template/grok/') {
          return jsonOk(GROK)
        }
        if (url === '/v1/agent-templates/validate/') {
          return jsonOk({ ...SHIPPED_STOREFRONT_BEE, object: 'agent_template' })
        }
        if (url === '/v1/agent-templates/from-grok/') {
          return jsonOk({ ...SHIPPED_STOREFRONT_BEE, object: 'agent_template' })
        }
        if (url === '/v1/agents/codey/template/import/') {
          return jsonOk({
            object: 'agent_template_import',
            agent_id: 'codey',
            template: SHIPPED_STOREFRONT_BEE,
            applied: { profile: true, memories: 2, skills: 1, routines: 0, plugins: 0 },
          })
        }
        if (url === '/v1/agent-templates/import/' && method === 'POST') {
          return jsonOk({
            object: 'agent_template_import',
            created: true,
            agent_id: 'swarm-engineer',
            template: SHIPPED_SWARM_ENGINEER,
            applied: { profile: true, memories: 2, skills: 1, routines: 1, plugins: 1 },
            fill_ins_remaining: [{ key: 'owner_repo', label: 'GitHub owner/repo', required: true }],
            plugins_missing: ['web_search'],
          })
        }
        return jsonOk({ object: 'list', data: [] })
      }),
    )
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:template'),
      revokeObjectURL: vi.fn(),
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('renders the shipped gallery card and current-seat export', async () => {
    renderGallery()
    expect(screen.getByRole('dialog', { name: 'Templates' })).toBeInTheDocument()
    const cards = screen.getAllByTestId('os-template-card')
    expect(cards.map((card) => card.getAttribute('data-item-id'))).toEqual(
      expect.arrayContaining(['shipped-storefront-bee', 'shipped-swarm-engineer']),
    )
    expect(screen.getByTestId('os-templates-scope')).toHaveTextContent(/Org scopes wait on #1311/)
    expect(screen.getByTestId('os-templates-share')).toHaveTextContent(/Share ids are not supported/)
    expect(screen.getByTestId('os-templates-drawer')).toHaveTextContent('welcome-tour')
    expect(screen.getByLabelText('Install onto seat')).toHaveValue('codey')
    await waitFor(() => {
      expect(screen.getAllByTestId('os-template-card').some((el) => el.getAttribute('data-source') === 'seat')).toBe(
        true,
      )
    })
  })

  it('validates then installs the shipped pack onto the current seat', async () => {
    renderGallery()
    fireEvent.click(screen.getByTestId('os-templates-validate'))
    await waitFor(() => {
      expect(screen.getByTestId('os-templates-status')).toHaveAttribute('data-status', 'ok')
    })
    expect(screen.getByTestId('os-templates-status')).toHaveTextContent(/secret-free/i)
    expect(screen.getByTestId('os-templates-validated')).toHaveTextContent('Storefront Bee')
    fireEvent.click(screen.getByTestId('os-templates-install'))
    await waitFor(() => {
      expect(screen.getByTestId('os-templates-status')).toHaveTextContent(/2 memories, 1 skill/)
    })
    const fetchMock = vi.mocked(fetch)
    const importCall = fetchMock.mock.calls.find((call) => String(call[0]).includes('/template/import/'))
    expect(importCall?.[0]).toBe('/v1/agents/codey/template/import/')
    expect(JSON.parse(String(importCall?.[1]?.body))).toMatchObject({ kind: 'agent_template' })
    expect(JSON.stringify(importCall?.[1]?.body)).not.toMatch(/sk-|api_key/i)
  })

  it('surfaces secret validation failures and does not install', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url === '/v1/agent-templates/validate/') {
          return jsonErr(400, 'template must not contain credential-shaped strings', 'template_secrets')
        }
        if (url.includes('/template/import/')) {
          throw new Error('import must not run')
        }
        return jsonOk({ ...SHIPPED_STOREFRONT_BEE, object: 'agent_template' })
      }),
    )
    renderGallery()
    fireEvent.click(screen.getByTestId('os-templates-validate'))
    await waitFor(() => {
      expect(screen.getByTestId('os-templates-status')).toHaveAttribute('data-status', 'fail')
    })
    expect(screen.getByTestId('os-templates-status')).toHaveTextContent(/credential-shaped/)
    expect(vi.mocked(fetch).mock.calls.every((call) => !String(call[0]).includes('/import/'))).toBe(true)
  })

  it('loads pasted Grok JSON through from-grok then import', async () => {
    renderGallery()
    fireEvent.change(screen.getByLabelText('Paste template JSON'), {
      target: { value: JSON.stringify(GROK) },
    })
    fireEvent.click(screen.getByTestId('os-templates-load-paste'))
    const pasted = screen.getAllByTestId('os-template-card').find((el) => el.getAttribute('data-source') === 'paste')
    expect(pasted).toBeTruthy()
    fireEvent.click(screen.getByTestId('os-templates-validate'))
    await waitFor(() => {
      expect(screen.getByTestId('os-templates-status')).toHaveAttribute('data-status', 'ok')
    })
    const fetchMock = vi.mocked(fetch)
    expect(fetchMock.mock.calls.some((call) => String(call[0]) === '/v1/agent-templates/from-grok/')).toBe(true)
    fireEvent.click(screen.getByTestId('os-templates-install'))
    await waitFor(() => {
      expect(screen.getByTestId('os-templates-status')).toHaveTextContent(/Installed profile/)
    })
    const importCall = fetchMock.mock.calls.find((call) => String(call[0]).includes('/template/import/'))
    const body = JSON.parse(String(importCall?.[1]?.body))
    expect(body.kind).toBe('agent_template')
    expect(body.profile.display_name).toBe('Storefront Bee')
    expect(JSON.stringify(body)).not.toMatch(/grok_bot_template/)
  })

  it('disables install without a bare seat and warns on scoped current agents', () => {
    publishCurrentAgent({ id: 'team:lab', kind: 'api' })
    renderGallery()
    expect(screen.getByTestId('os-templates-scoped-hint')).toHaveTextContent(/bare agent id/)
    expect(screen.getByTestId('os-templates-install')).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Install onto seat'), { target: { value: 'fresh' } })
    expect(screen.getByTestId('os-templates-install')).toBeEnabled()
  })

  it('exports the current seat pack and Grok projection', async () => {
    const click = vi.fn()
    const original = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = original(tag)
      if (tag === 'a') el.click = click
      return el
    })
    renderGallery()
    fireEvent.click(screen.getByTestId('os-templates-export'))
    await waitFor(() => {
      expect(screen.getByTestId('os-templates-status')).toHaveTextContent(/secret-free pack/)
    })
    fireEvent.click(screen.getByTestId('os-templates-export-grok'))
    await waitFor(() => {
      expect(screen.getByTestId('os-templates-status')).toHaveTextContent(/Grok Bot projection/)
    })
    expect(click).toHaveBeenCalled()
    const urls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]))
    expect(urls).toContain('/v1/agents/codey/template/')
    expect(urls).toContain('/v1/agents/codey/template/grok/')
  })

  it('creates a Swarm Engineer agent and shows fill-ins, connect, and kickoff', async () => {
    renderGallery()
    const engineer = screen.getAllByTestId('os-template-card').find(
      (el) => el.getAttribute('data-item-id') === 'shipped-swarm-engineer',
    )
    expect(engineer).toBeTruthy()
    fireEvent.click(engineer!)
    fireEvent.click(screen.getByTestId('os-templates-create'))
    await waitFor(() => {
      expect(screen.getByTestId('os-templates-result')).toBeInTheDocument()
    })
    expect(screen.getByTestId('os-templates-agent-link')).toHaveTextContent('swarm-engineer')
    expect(screen.getByTestId('os-templates-fill-ins')).toHaveTextContent(/owner_repo/)
    expect(screen.getByTestId('os-templates-fill-ins')).toHaveTextContent(/pending/)
    expect(screen.getByTestId('os-templates-connect')).toHaveTextContent(/web_search/)
    expect(screen.getByTestId('os-templates-kickoff')).toHaveTextContent('implement-issue')
    const urls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]))
    expect(urls).toContain('/v1/agent-templates/import/')
  })

  it('opens domain editors from the export wizard', () => {
    const events: string[] = []
    const onEvent = (event: Event) => events.push(event.type)
    window.addEventListener('swarm:open-agent-editor', onEvent)
    window.addEventListener('swarm:open-computer-control', onEvent)
    window.addEventListener('swarm:open-plugins', onEvent)
    renderGallery()
    fireEvent.click(screen.getByTestId('os-templates-open-profile'))
    fireEvent.click(screen.getByTestId('os-templates-open-routines'))
    fireEvent.click(screen.getByTestId('os-templates-open-plugins'))
    expect(events).toEqual([
      'swarm:open-agent-editor',
      'swarm:open-computer-control',
      'swarm:open-plugins',
    ])
    window.removeEventListener('swarm:open-agent-editor', onEvent)
    window.removeEventListener('swarm:open-computer-control', onEvent)
    window.removeEventListener('swarm:open-plugins', onEvent)
  })

  it('replaces a create checklist when a later install finishes', async () => {
    renderGallery()
    const engineer = screen.getAllByTestId('os-template-card').find(
      (el) => el.getAttribute('data-item-id') === 'shipped-swarm-engineer',
    )
    fireEvent.click(engineer!)
    fireEvent.click(screen.getByTestId('os-templates-create'))
    await waitFor(() => {
      expect(screen.getByTestId('os-templates-agent-link')).toHaveTextContent('swarm-engineer')
    })
    fireEvent.click(screen.getByTestId('os-templates-install'))
    await waitFor(() => {
      expect(screen.getByTestId('os-templates-agent-link')).toHaveTextContent('codey')
    })
    expect(screen.getByTestId('os-templates-fill-ins')).toHaveTextContent(/No fill-ins pending/)
    expect(screen.getByTestId('os-templates-kickoff')).toHaveTextContent('welcome-tour')
    expect(screen.getByTestId('os-templates-kickoff')).not.toHaveTextContent('implement-issue')
  })

  it('drops an install result that arrives after close', async () => {
    let release: ((value: Response) => void) | null = null
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/template/import/')) {
          return new Promise<Response>((resolve) => {
            release = resolve
          })
        }
        return jsonOk({ ...SHIPPED_STOREFRONT_BEE, object: 'agent_template' })
      }),
    )
    renderGallery()
    fireEvent.click(screen.getByTestId('os-templates-install'))
    await waitFor(() => {
      expect(screen.getByTestId('os-templates-status')).toHaveTextContent('Installing…')
    })
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(release).toBeTruthy()
    expect(screen.getByTestId('os-templates-status')).not.toHaveTextContent('Installing…')
    await act(async () => {
      release!(
        jsonOk({
          object: 'agent_template_import',
          agent_id: 'late-agent',
          template: SHIPPED_STOREFRONT_BEE,
          applied: { profile: true, memories: 9, skills: 9, routines: 9, plugins: 9 },
        }),
      )
    })
    expect(screen.queryByTestId('os-templates-agent-link')).not.toBeInTheDocument()
    expect(screen.getByTestId('os-templates-status')).not.toHaveTextContent(/9 memories/)
    expect(screen.queryByText('late-agent')).not.toBeInTheDocument()
  })

  it('closes on Escape without becoming a route', () => {
    const { onClose } = renderGallery()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  it('renders nothing when closed', () => {
    renderGallery(false)
    expect(screen.queryByTestId('os-templates-gallery')).not.toBeInTheDocument()
  })
})
