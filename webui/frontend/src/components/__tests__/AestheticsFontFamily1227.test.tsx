import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../DaisyUI'
import { AestheticsPane } from '../settings/panes/AestheticsPane'
import {
  CUSTOM_FONT_FAMILY_STORAGE_KEY,
  FONT_FAMILY_STORAGE_KEY,
  OS_FONT_FAMILY_ATTR,
  OS_FONT_FAMILY_VAR,
} from '../../lib/fontFamily'

function renderPane() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AestheticsPane />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

function stubFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ object: 'user_preferences', empty: false }),
    } as Response),
  )
}

function rootVar(): string {
  return document.documentElement.style.getPropertyValue(OS_FONT_FAMILY_VAR)
}

describe('#1227: Aesthetics font-family selector', () => {
  afterEach(() => {
    localStorage.removeItem(FONT_FAMILY_STORAGE_KEY)
    localStorage.removeItem(CUSTOM_FONT_FAMILY_STORAGE_KEY)
    document.documentElement.style.removeProperty(OS_FONT_FAMILY_VAR)
    document.documentElement.removeAttribute(OS_FONT_FAMILY_ATTR)
    vi.unstubAllGlobals()
  })

  it('renders the ticket presets defaulting to Omarchy', () => {
    stubFetch()
    renderPane()
    const select = screen.getByRole('combobox', { name: 'Font family' }) as HTMLSelectElement
    expect(Array.from(select.options).map((o) => o.value)).toEqual([
      'omarchy',
      'hack',
      'monospace',
      'sans',
      'serif',
      'custom',
    ])
    expect(select).toHaveValue('omarchy')
  })

  it('persists the choice and sets the root variable + attribute', () => {
    stubFetch()
    renderPane()
    fireEvent.change(screen.getByRole('combobox', { name: 'Font family' }), {
      target: { value: 'serif' },
    })
    expect(localStorage.getItem(FONT_FAMILY_STORAGE_KEY)).toBe('serif')
    expect(rootVar()).toContain('ui-serif')
    expect(document.documentElement.getAttribute(OS_FONT_FAMILY_ATTR)).toBe('serif')
  })

  it('reveals a custom stack input and applies the typed value', () => {
    stubFetch()
    renderPane()
    const select = screen.getByRole('combobox', { name: 'Font family' })
    fireEvent.change(select, { target: { value: 'custom' } })
    const input = screen.getByRole('textbox', { name: 'Custom font stack' })
    fireEvent.change(input, { target: { value: "'Fira Code', monospace" } })
    expect(localStorage.getItem(FONT_FAMILY_STORAGE_KEY)).toBe('custom')
    expect(localStorage.getItem(CUSTOM_FONT_FAMILY_STORAGE_KEY)).toBe(
      "'Fira Code', monospace",
    )
    expect(rootVar()).toContain('Fira Code')
    expect(document.documentElement.getAttribute(OS_FONT_FAMILY_ATTR)).toBe('custom')
  })

  it('reverting to the default preset removes the custom input', () => {
    stubFetch()
    renderPane()
    const select = screen.getByRole('combobox', { name: 'Font family' })
    fireEvent.change(select, { target: { value: 'custom' } })
    expect(screen.getByRole('textbox', { name: 'Custom font stack' })).toBeInTheDocument()
    fireEvent.change(select, { target: { value: 'omarchy' } })
    expect(screen.queryByRole('textbox', { name: 'Custom font stack' })).toBeNull()
    expect(rootVar()).toContain("'JetBrainsMono Nerd Font'")
  })
})
