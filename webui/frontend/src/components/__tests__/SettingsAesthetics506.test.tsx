import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SettingsSheet, { settingsDetailFromQuery } from '../SettingsSheet'
import { ToastProvider } from '../DaisyUI'
import {
  ACTION_ROW_LABELS_STORAGE_KEY,
  loadActionRowLabels,
} from '../../lib/actionRowLabels'
import { BUBBLE_THEME_STORAGE_KEY } from '../../lib/bubbleTheme'

function renderSheet() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const onClose = vi.fn()
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <SettingsSheet isOpen onClose={onClose} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

function openAesthetics() {
  fireEvent.click(screen.getByRole('button', { name: 'Aesthetics' }))
}

describe('#506: Settings Aesthetics section', () => {
  afterEach(() => {
    localStorage.removeItem(BUBBLE_THEME_STORAGE_KEY)
    localStorage.removeItem(ACTION_ROW_LABELS_STORAGE_KEY)
    vi.unstubAllGlobals()
  })

  it('is deep-linkable via settingsDetailFromQuery and the nav', () => {
    expect(settingsDetailFromQuery('aesthetics')).toEqual({ section: 'aesthetics' })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ data: [] }),
      } as Response),
    )
    renderSheet()
    expect(screen.getByRole('button', { name: 'Aesthetics' })).toBeInTheDocument()
    openAesthetics()
    expect(screen.getByText('Chat presentation: bubble theme and message action buttons.')).toBeInTheDocument()
  })

  it('renders the bubble-theme picker from the registry (no hardcoded ids)', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ data: [] }),
      } as Response),
    )
    renderSheet()
    openAesthetics()
    const select = screen.getByRole('combobox', { name: 'Bubble theme' }) as HTMLSelectElement
    const options = Array.from(select.options).map((option) => option.value)
    // All registered themes, registry order (#808: feed retired).
    expect(options).toEqual(['speech', 'simple', 'irc'])
    expect(select).toHaveValue('speech') // DEFAULT_BUBBLE_THEME when unset
  })

  it('writing the bubble theme persists through saveBubbleTheme', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ data: [] }),
      } as Response),
    )
    renderSheet()
    openAesthetics()
    fireEvent.change(screen.getByRole('combobox', { name: 'Bubble theme' }), {
      target: { value: 'irc' },
    })
    expect(localStorage.getItem(BUBBLE_THEME_STORAGE_KEY)).toBe('irc')
  })

  it('labels toggle defaults ON and writes through saveActionRowLabels', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ data: [] }),
      } as Response),
    )
    renderSheet()
    openAesthetics()
    const toggle = screen.getByRole('checkbox', { name: 'Action-row button labels' })
    expect(toggle).toBeChecked() // default ON
    fireEvent.click(toggle)
    expect(toggle).not.toBeChecked()
    expect(loadActionRowLabels()).toBe(false)
    fireEvent.click(toggle)
    expect(loadActionRowLabels()).toBe(true)
  })
})
