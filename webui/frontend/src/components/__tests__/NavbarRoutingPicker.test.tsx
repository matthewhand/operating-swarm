import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ComponentProps } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { NavbarRoutingPicker } from '../NavbarRoutingPicker'

const { fetchCliModelsMock } = vi.hoisted(() => ({
  fetchCliModelsMock: vi.fn(async (cli: string) => ({ cli, models: [] as string[] })),
}))

vi.mock('../../lib/api', () => ({
  fetchCliModels: (...args: [string]) => fetchCliModelsMock(...args),
}))

const AGY_MODELS = [
  'gemini-3.8-flash-high',
  'gemini-3.8-flash-medium',
  'claude-sonnet-4-6',
  'default',
]

function renderPicker(
  props: Partial<ComponentProps<typeof NavbarRoutingPicker>> = {},
) {
  const onChange = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(
    <QueryClientProvider client={client}>
      <NavbarRoutingPicker
        seatKind="cli"
        agents={[
          { id: 'agy', label: 'agy' },
          { id: 'grok', label: 'grok' },
        ]}
        selectedAgent="agy"
        models={AGY_MODELS}
        selectedModel="gemini-3.8-flash-medium"
        preferredEffort="medium"
        onChange={onChange}
        footerAction={{ id: '__manage_cli__', label: 'Manage CLI', onSelect: vi.fn() }}
        {...props}
      />
    </QueryClientProvider>,
  )
  return { onChange, ...view }
}

describe('NavbarRoutingPicker (REQ-200)', () => {
  const originalMatchMedia = window.matchMedia

  afterEach(() => {
    document.documentElement.removeAttribute('dir')
    if (originalMatchMedia) window.matchMedia = originalMatchMedia
    else delete (window as { matchMedia?: unknown }).matchMedia
    fetchCliModelsMock.mockReset()
    fetchCliModelsMock.mockImplementation(async (cli: string) => ({ cli, models: [] }))
  })

  it('renders one control with three pills and no sibling selects', () => {
    renderPicker()
    expect(screen.getByTestId('navbar-routing-picker')).toBeInTheDocument()
    expect(screen.getAllByTestId('navbar-routing-picker')).toHaveLength(1)
    expect(screen.getByTestId('routing-pill-agent')).toHaveTextContent('agy')
    expect(screen.getByTestId('routing-pill-model')).toHaveTextContent('gemini-3.8-flash')
    expect(screen.getByTestId('routing-pill-effort')).toHaveTextContent('medium')
    expect(screen.getByTestId('routing-face')).toHaveAttribute(
      'title',
      'agy / gemini-3.8-flash / medium',
    )
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.queryByText('You')).not.toBeInTheDocument()
    expect(screen.queryByText('Default')).not.toBeInTheDocument()
  })

  it('hides the chevron until hover and opens that dimension only', () => {
    renderPicker()
    const effort = screen.getByTestId('routing-pill-effort')
    const chevron = effort.querySelector('.os-routing-pill__chevron')
    expect(chevron).toBeTruthy()
    fireEvent.mouseEnter(effort)
    expect(screen.getByTestId('routing-menu-effort')).toBeInTheDocument()
    expect(screen.queryByTestId('routing-menu-agent')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: 'high' }))
  })

  it('changes effort alone without clearing agent or model', () => {
    const { onChange } = renderPicker()
    fireEvent.click(screen.getByTestId('routing-pill-effort'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'high' }))
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        changed: 'effort',
        agent: 'agy',
        model: 'gemini-3.8-flash-high',
        modelBase: 'gemini-3.8-flash',
        effort: 'high',
      }),
    )
  })

  it('re-prompts effort after a model that exposes it', () => {
    const { onChange } = renderPicker()
    fireEvent.click(screen.getByTestId('routing-pill-model'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'gemini-3.8-flash' }))
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        changed: 'model',
        modelBase: 'gemini-3.8-flash',
        effort: 'medium',
      }),
    )
    expect(screen.getByTestId('routing-menu-effort')).toBeInTheDocument()
  })

  it('skips effort for a model family without it', () => {
    const { onChange } = renderPicker()
    fireEvent.click(screen.getByTestId('routing-pill-model'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'claude-sonnet-4-6' }))
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        changed: 'model',
        model: 'claude-sonnet-4-6',
        effort: null,
      }),
    )
    expect(screen.queryByTestId('routing-menu-effort')).not.toBeInTheDocument()
  })

  it('opens the full cascade from the agent pill and supports keyboard', () => {
    renderPicker()
    const agent = screen.getByTestId('routing-pill-agent')
    fireEvent.click(agent)
    const menu = screen.getByTestId('routing-menu-agent')
    expect(within(menu).getByRole('menuitem', { name: 'agy' })).toBeInTheDocument()
    expect(within(menu).getByRole('menuitem', { name: 'grok' })).toBeInTheDocument()
    expect(within(menu).getByRole('menuitem', { name: 'Manage CLI' })).toBeInTheDocument()
    const picker = screen.getByTestId('navbar-routing-picker')
    fireEvent.keyDown(picker, { key: 'ArrowDown' })
    fireEvent.keyDown(picker, { key: 'Enter' })
    fireEvent.keyDown(picker, { key: 'Escape' })
    expect(screen.queryByTestId('routing-menu-agent')).not.toBeInTheDocument()
  })

  it('uses a sheet on narrow viewports', () => {
    const mq = {
      matches: true,
      media: '(max-width: 1023px)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
      onchange: null,
    }
    window.matchMedia = vi.fn().mockImplementation(() => mq) as unknown as typeof window.matchMedia
    renderPicker()
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    expect(screen.getByTestId('routing-sheet')).toBeInTheDocument()
  })

  const emptyModelsNoFamilies = {
    models: [] as string[],
    selectedModel: '',
    modelWarning: 'grok: no models advertised',
  }

  it('narrow sheet keeps an explicit Model request when no families are known yet (#275)', () => {
    const mq = {
      matches: true,
      media: '(max-width: 1023px)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
      onchange: null,
    }
    window.matchMedia = vi.fn().mockImplementation(() => mq) as unknown as typeof window.matchMedia
    // The model pill is rendered because a probe warning exists, yet there are no
    // families — the old level fallback swapped in the agent list here.
    renderPicker(emptyModelsNoFamilies)
    fireEvent.click(screen.getByTestId('routing-pill-model'))
    expect(screen.getByTestId('routing-sheet')).toBeInTheDocument()
    expect(screen.getByTestId('routing-menu-model')).toBeInTheDocument()
    expect(screen.getByTestId('routing-model-warning')).toHaveTextContent(
      'grok: no models advertised',
    )
    expect(screen.queryByTestId('routing-menu-agent')).not.toBeInTheDocument()
  })

  it('wide flyout keeps an explicit Model request when no families are known yet (#275)', () => {
    renderPicker(emptyModelsNoFamilies)
    fireEvent.click(screen.getByTestId('routing-pill-model'))
    expect(screen.queryByTestId('routing-sheet')).not.toBeInTheDocument()
    expect(screen.getByTestId('routing-menu-model')).toBeInTheDocument()
    expect(screen.getByTestId('routing-model-warning')).toHaveTextContent(
      'grok: no models advertised',
    )
    expect(screen.queryByTestId('routing-menu-agent')).not.toBeInTheDocument()
  })

  it('desktop hover on the model pill opens the model menu, not the agent list (#275)', () => {
    renderPicker(emptyModelsNoFamilies)
    fireEvent.mouseEnter(screen.getByTestId('routing-pill-agent'))
    expect(screen.getByTestId('routing-menu-agent')).toBeInTheDocument()
    fireEvent.mouseEnter(screen.getByTestId('routing-pill-model'))
    expect(screen.getByTestId('routing-menu-model')).toBeInTheDocument()
    expect(screen.queryByTestId('routing-menu-agent')).not.toBeInTheDocument()
  })

  it('model pill click is not stolen by the routing-face agent fallback (#275)', () => {
    renderPicker(emptyModelsNoFamilies)
    fireEvent.click(screen.getByTestId('routing-pill-model'))
    // Face onClick must not replace the model menu with the CLI provider list.
    fireEvent.click(screen.getByTestId('routing-face'))
    expect(screen.getByTestId('routing-menu-model')).toBeInTheDocument()
    expect(screen.queryByTestId('routing-menu-agent')).not.toBeInTheDocument()
  })

  it('lists pi provider/model ids as pin-able model options (#103)', () => {
    const { onChange } = renderPicker({
      agents: [
        { id: 'pi', label: 'pi' },
        { id: 'grok', label: 'grok' },
      ],
      selectedAgent: 'pi',
      models: ['openai/gpt-4o', 'anthropic/claude-sonnet-4-6'],
      selectedModel: 'openai/gpt-4o',
      preferredEffort: undefined,
    })
    expect(screen.getByTestId('routing-pill-model')).toHaveTextContent('openai/gpt-4o')
    fireEvent.click(screen.getByTestId('routing-pill-model'))
    expect(screen.getByRole('menuitem', { name: 'openai/gpt-4o' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'anthropic/claude-sonnet-4-6' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'openai' })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'default' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: 'anthropic/claude-sonnet-4-6' }))
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        changed: 'model',
        agent: 'pi',
        model: 'anthropic/claude-sonnet-4-6',
        modelBase: 'anthropic/claude-sonnet-4-6',
        effort: null,
      }),
    )
  })

  it('shows a probe warning instead of option default when models are empty', async () => {
    renderPicker({
      models: [],
      selectedModel: '',
      modelWarning: "grok: CLI not installed (no 'grok' on PATH)",
    })
    fireEvent.click(screen.getByTestId('routing-pill-model'))
    expect(await screen.findByTestId('routing-model-warning')).toHaveTextContent(
      "grok: CLI not installed (no 'grok' on PATH)",
    )
    expect(screen.queryByRole('menuitem', { name: 'default' })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Default' })).not.toBeInTheDocument()
  })

  it('puts a separator then Manage CLI last without a nested model flyout', () => {
    const onSelect = vi.fn()
    renderPicker({
      footerAction: { id: '__manage_cli__', label: 'Manage CLI', onSelect },
    })
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    const menu = screen.getByTestId('routing-menu-agent')
    const items = within(menu).getAllByRole('menuitem')
    expect(items.map((item) => item.getAttribute('data-testid'))).toEqual([
      'routing-option-agent-agy',
      'routing-option-agent-grok',
      'routing-option-agent-__manage_cli__',
    ])
    expect(items[items.length - 1]).toHaveAccessibleName('Manage CLI')
    const divider = within(menu).getByTestId('manage-surface-divider')
    expect(divider).toHaveAttribute('role', 'separator')
    const manage = items[items.length - 1]
    expect(manage.compareDocumentPosition(divider) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy()
    expect(manage).not.toHaveAttribute('aria-haspopup')
    expect(within(manage).queryByText('›')).not.toBeInTheDocument()
    fireEvent.mouseEnter(manage)
    fireEvent.keyDown(screen.getByTestId('navbar-routing-picker'), { key: 'ArrowRight' })
    expect(manage).not.toHaveAttribute('aria-haspopup')
    fireEvent.click(manage)
    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(screen.queryByTestId('routing-menu-agent')).not.toBeInTheDocument()
  })

  it('API seat opens the searchable model palette, not the agent dropdown (#281)', () => {
    const { onChange } = renderPicker({
      seatKind: 'api',
      agents: [
        { id: 'orchestration', label: 'Orchestration' },
        { id: 'gpt-4o', label: 'gpt-4o' },
        { id: 'anthropic/claude-3-5-sonnet', label: 'claude-3-5-sonnet' },
      ],
      selectedAgent: 'orchestration',
      models: [],
      selectedModel: '',
      defaultAgent: 'orchestration',
      footerAction: undefined,
    })
    expect(screen.getByTestId('routing-pill-agent')).toHaveTextContent('Orchestration')
    fireEvent.mouseEnter(screen.getByTestId('routing-pill-agent'))
    expect(screen.queryByTestId('os-model-search-palette')).not.toBeInTheDocument()
    expect(screen.queryByTestId('routing-menu-agent')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    const palette = screen.getByTestId('os-model-search-palette')
    expect(palette).toHaveClass('os-search-palette')
    expect(screen.queryByTestId('routing-menu-agent')).not.toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Filter models' })).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('os-model-row-gpt-4o'))
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ changed: 'agent', agent: 'gpt-4o' }),
    )
    expect(screen.queryByTestId('os-model-search-palette')).not.toBeInTheDocument()
  })

  it('opens nested menus toward inline-start in RTL', () => {
    document.documentElement.setAttribute('dir', 'rtl')
    renderPicker()
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    const picker = screen.getByTestId('navbar-routing-picker')
    fireEvent.keyDown(picker, { key: 'ArrowLeft' })
    expect(screen.getByTestId('routing-menu-model')).toBeInTheDocument()
    document.documentElement.removeAttribute('dir')
  })

  it('shows Loading... with a spinner while CLI models are fetching (REQ-870)', async () => {
    fetchCliModelsMock.mockReturnValue(new Promise(() => {}))
    renderPicker({ models: [], selectedModel: '', modelWarning: undefined })
    fireEvent.click(screen.getByTestId('routing-pill-model'))
    const loading = await screen.findByTestId('routing-model-loading')
    expect(loading).toHaveTextContent('Loading...')
    expect(loading.querySelector('.loading-spinner')).toBeTruthy()
    expect(screen.queryByText('No options')).not.toBeInTheDocument()
    expect(screen.queryByText('No models discovered')).not.toBeInTheDocument()
    expect(screen.queryByTestId('routing-model-warning')).not.toBeInTheDocument()
  })

  it('suppresses a premature empty warning while models are in flight', async () => {
    fetchCliModelsMock.mockReturnValue(new Promise(() => {}))
    renderPicker({
      models: [],
      selectedModel: '',
      modelWarning: 'No models discovered',
    })
    fireEvent.click(screen.getByTestId('routing-pill-model'))
    expect(await screen.findByTestId('routing-model-loading')).toHaveTextContent(
      'Loading...',
    )
    expect(screen.queryByTestId('routing-model-warning')).not.toBeInTheDocument()
    expect(screen.queryByText('No options')).not.toBeInTheDocument()
  })

  it('replaces Loading... with fetched model options', async () => {
    let resolveFetch: (value: { cli: string; models: string[] }) => void = () => {}
    fetchCliModelsMock.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve
      }),
    )
    renderPicker({ models: [], selectedModel: '' })
    fireEvent.click(screen.getByTestId('routing-pill-model'))
    expect(await screen.findByTestId('routing-model-loading')).toBeInTheDocument()
    resolveFetch({ cli: 'agy', models: ['qwen2.5-coder:32b', 'qwen2.5-coder:7b'] })
    await waitFor(() => {
      expect(screen.queryByTestId('routing-model-loading')).not.toBeInTheDocument()
    })
    expect(screen.getByRole('menuitem', { name: 'qwen2.5-coder:32b' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'qwen2.5-coder:7b' })).toBeInTheDocument()
  })
})
