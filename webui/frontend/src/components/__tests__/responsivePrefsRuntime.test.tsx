/**
 * #833 — runtime wiring: shell data-viewport attribute, tier-aware
 * action-row visibility, and the Settings tabulated control.
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import MessageRowActions from '../MessageRowActions'
import SettingsSheet from '../SettingsSheet'
import { ToastProvider } from '../DaisyUI'
import {
  ACTIONS_VISIBLE_STORAGE_KEY,
  saveActionsAlwaysVisible,
} from '../../lib/responsivePrefs'

function setTier(width: number) {
  act(() => {
    window.innerWidth = width
    window.dispatchEvent(new Event('resize'))
  })
}

describe('#833 — action rows follow the viewport tier', () => {
  it('desktop defaults to hover-reveal; touch tiers are always visible', () => {
    localStorage.removeItem(ACTIONS_VISIBLE_STORAGE_KEY)
    const { container } = render(
      <ToastProvider>
        <MessageRowActions text="hello" />
      </ToastProvider>,
    )
    const row = container.querySelector('[data-testid="os-message-row-actions"]')
    // jsdom opens at 1024 → desktop → hover-reveal (no always-visible mark).
    expect(row).not.toHaveAttribute('data-always-visible')

    setTier(390) // mobile
    // React re-renders on the tier change only if the component re-mounts;
    // the hook subscribes live, so the attribute flips without remount.
    expect(row).toHaveAttribute('data-always-visible', 'true')
    localStorage.removeItem(ACTIONS_VISIBLE_STORAGE_KEY)
  })

  it('a saved per-tier override wins over the shipped default', () => {
    // Force always-visible ON for desktop.
    saveActionsAlwaysVisible({ mobile: true, tablet: true, desktop: true })
    const { container } = render(
      <ToastProvider>
        <MessageRowActions text="hello" />
      </ToastProvider>,
    )
    const row = container.querySelector('[data-testid="os-message-row-actions"]')
    expect(row).toHaveAttribute('data-always-visible', 'true')
    localStorage.removeItem(ACTIONS_VISIBLE_STORAGE_KEY)
  })

  it('Settings → Aesthetics exposes the tabulated per-tier control', () => {
    localStorage.removeItem(ACTIONS_VISIBLE_STORAGE_KEY)
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ToastProvider>
          <SettingsSheet isOpen initialSection="aesthetics" onClose={() => {}} />
        </ToastProvider>
      </QueryClientProvider>,
    )
    for (const tier of ['mobile', 'tablet', 'desktop']) {
      expect(screen.getByTestId(`viewport-actions-${tier}`)).toBeInTheDocument()
    }
    // Touch tiers default checked, desktop unchecked.
    expect(screen.getByTestId('viewport-actions-mobile')).toBeChecked()
    expect(screen.getByTestId('viewport-actions-tablet')).toBeChecked()
    expect(screen.getByTestId('viewport-actions-desktop')).not.toBeChecked()
  })

  it('toggling a tier in Settings persists and notifies rows', () => {
    localStorage.removeItem(ACTIONS_VISIBLE_STORAGE_KEY)
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ToastProvider>
          <SettingsSheet isOpen initialSection="aesthetics" onClose={() => {}} />
        </ToastProvider>
      </QueryClientProvider>,
    )
    const desktop = screen.getByTestId('viewport-actions-desktop')
    fireEvent.click(desktop)
    expect(desktop).toBeChecked()
    const stored = JSON.parse(
      localStorage.getItem(ACTIONS_VISIBLE_STORAGE_KEY) ?? '{}',
    )
    expect(stored.desktop).toBe(true)
    localStorage.removeItem(ACTIONS_VISIBLE_STORAGE_KEY)
  })
})
