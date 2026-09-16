import { describe, it, expect, vi, afterEach } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import type { ComponentProps } from 'react'
import ModelSearchPalette from '../ModelSearchPalette'
import { OPEN_SETTINGS_EVENT } from '../SettingsSheet'
import {
  filterModelOptions,
  groupModelOptions,
  modelProviderGroup,
  type ModelSearchOption,
} from '../../lib/modelSearch'

const MODELS: ModelSearchOption[] = [
  { id: 'orchestration', label: 'Orchestration' },
  { id: 'auxiliary', label: 'Auxiliary' },
  { id: 'gpt-4o', label: 'gpt-4o', tag: 'chat' },
  { id: 'anthropic/claude-3-5-sonnet', label: 'claude-3-5-sonnet' },
  { id: 'claude-sonnet-4-6', label: 'claude-sonnet-4-6' },
  { id: 'gemini-2.0-flash', label: 'gemini-2.0-flash' },
  { id: 'deepseek-chat', label: 'deepseek-chat' },
]

function renderPalette(
  extras: Partial<ComponentProps<typeof ModelSearchPalette>> = {},
) {
  const onClose = vi.fn()
  const onSelect = vi.fn()
  const view = render(
    <ModelSearchPalette
      open
      models={MODELS}
      selectedId="orchestration"
      defaultId="orchestration"
      onClose={onClose}
      onSelect={onSelect}
      {...extras}
    />,
  )
  return { onClose, onSelect, ...view }
}

describe('modelSearch grouping (#281)', () => {
  it('groups LiteLLM prefixes and named profiles', () => {
    expect(modelProviderGroup('anthropic/claude-3-5-sonnet')).toBe('anthropic')
    expect(modelProviderGroup('gpt-4o')).toBe('openai')
    expect(modelProviderGroup('claude-sonnet-4-6')).toBe('anthropic')
    expect(modelProviderGroup('gemini-2.0-flash')).toBe('gemini')
    expect(modelProviderGroup('deepseek-chat')).toBe('deepseek')
    expect(modelProviderGroup('orchestration')).toBe('Profiles')
    expect(modelProviderGroup('gpt-4o', 'custom')).toBe('custom')
  })

  it('filters by name, provider prefix, and tag', () => {
    expect(filterModelOptions(MODELS, 'claude').map((row) => row.id)).toEqual([
      'anthropic/claude-3-5-sonnet',
      'claude-sonnet-4-6',
    ])
    expect(filterModelOptions(MODELS, 'anthropic/').map((row) => row.id)).toEqual([
      'anthropic/claude-3-5-sonnet',
      'claude-sonnet-4-6',
    ])
    expect(filterModelOptions(MODELS, 'gpt-').map((row) => row.id)).toEqual(['gpt-4o'])
    expect(filterModelOptions(MODELS, 'chat').map((row) => row.id)).toEqual(
      expect.arrayContaining(['gpt-4o', 'deepseek-chat']),
    )
  })

  it('orders known providers before the Profiles bucket', () => {
    const names = groupModelOptions(MODELS).map((group) => group.name)
    expect(names[0]).toBe('openai')
    expect(names).toContain('anthropic')
    expect(names[names.length - 1]).toBe('Profiles')
  })
})

describe('ModelSearchPalette', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('opens as an os-search-palette with grouped rows and the current model marked', () => {
    renderPalette()
    const dialog = screen.getByRole('dialog', { name: 'Models' })
    expect(dialog).toHaveClass('os-search-palette')
    expect(dialog).toHaveClass('os-search-palette--centered')
    expect(screen.getByTestId('os-model-search-overlay')).toHaveClass(
      'os-search-overlay--centered',
    )
    expect(screen.getByRole('combobox', { name: 'Filter models' })).toHaveAttribute(
      'placeholder',
      'Search models',
    )
    expect(screen.getByTestId('os-model-group-openai')).toHaveTextContent('openai')
    expect(screen.getByTestId('os-model-group-anthropic')).toHaveTextContent('anthropic')
    expect(screen.getByTestId('os-model-group-Profiles')).toHaveTextContent('Profiles')
    const current = screen.getByTestId('os-model-row-orchestration')
    expect(current).toHaveAttribute('data-current', 'true')
    expect(current).toHaveAttribute('data-default', 'true')
    expect(current).toHaveAttribute('aria-current', 'true')
    expect(within(current).getByText('Default')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Manage API in Settings/i })).toBeInTheDocument()
  })

  it('filters models via the search input', () => {
    renderPalette()
    fireEvent.change(screen.getByRole('combobox', { name: 'Filter models' }), {
      target: { value: 'claude' },
    })
    const options = screen.getAllByRole('option')
    expect(options.map((row) => row.getAttribute('data-model-id'))).toEqual([
      'anthropic/claude-3-5-sonnet',
      'claude-sonnet-4-6',
    ])
    expect(screen.queryByTestId('os-model-row-gpt-4o')).not.toBeInTheDocument()
  })

  it('selects a model via click', () => {
    const { onSelect, onClose } = renderPalette()
    fireEvent.click(screen.getByTestId('os-model-row-gpt-4o'))
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'gpt-4o' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('selects the highlighted model via Enter', () => {
    const { onSelect, onClose } = renderPalette()
    fireEvent.change(screen.getByRole('combobox', { name: 'Filter models' }), {
      target: { value: 'deepseek' },
    })
    expect(screen.getByTestId('os-model-row-deepseek-chat')).toHaveAttribute(
      'aria-selected',
      'true',
    )
    fireEvent.keyDown(window, { key: 'Enter' })
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'deepseek-chat' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('navigates with arrows and closes on Escape', () => {
    const { onClose } = renderPalette()
    const first = screen.getAllByRole('option')[0]
    expect(first).toHaveAttribute('aria-selected', 'true')
    fireEvent.keyDown(window, { key: 'ArrowDown' })
    expect(screen.getAllByRole('option')[1]).toHaveAttribute('aria-selected', 'true')
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  it('launches Settings on the LLM profiles pane from the footer action', () => {
    const opened: Array<{ section?: string }> = []
    const onOpen = (event: Event) => {
      opened.push((event as CustomEvent<{ section?: string }>).detail ?? {})
    }
    window.addEventListener(OPEN_SETTINGS_EVENT, onOpen)
    const { onClose } = renderPalette()
    fireEvent.click(screen.getByTestId('os-model-manage-api'))
    window.removeEventListener(OPEN_SETTINGS_EVENT, onOpen)
    expect(onClose).toHaveBeenCalled()
    expect(opened).toEqual([{ section: 'llm-profiles' }])
  })

  it('shows an honest empty search state', () => {
    renderPalette()
    fireEvent.change(screen.getByRole('combobox', { name: 'Filter models' }), {
      target: { value: 'zzzz-no-such-model' },
    })
    expect(screen.getByText(/No matches for “zzzz-no-such-model”/)).toBeInTheDocument()
  })
})
