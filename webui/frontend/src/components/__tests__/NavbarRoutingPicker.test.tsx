import { fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ComponentProps } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { NavbarRoutingPicker } from '../NavbarRoutingPicker'

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
        footerAction={{ id: '__manage_cli__', label: 'Manage Cli', onSelect: vi.fn() }}
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
    expect(within(menu).getByRole('menuitem', { name: 'Manage Cli' })).toBeInTheDocument()
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
    renderPicker({
      models: [],
      selectedModel: '',
      modelWarning: 'grok: no models advertised',
    })
    fireEvent.click(screen.getByTestId('routing-pill-model'))
    expect(screen.getByTestId('routing-sheet')).toBeInTheDocument()
    expect(screen.getByTestId('routing-menu-model')).toBeInTheDocument()
    expect(screen.queryByTestId('routing-menu-agent')).not.toBeInTheDocument()
  })

  it('shows a probe warning instead of option default when models are empty', () => {
    renderPicker({
      models: [],
      selectedModel: '',
      modelWarning: "grok: CLI not installed (no 'grok' on PATH)",
    })
    fireEvent.click(screen.getByTestId('routing-pill-model'))
    expect(screen.getByTestId('routing-model-warning')).toHaveTextContent(
      "grok: CLI not installed (no 'grok' on PATH)",
    )
    expect(screen.queryByRole('menuitem', { name: 'default' })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Default' })).not.toBeInTheDocument()
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
})
