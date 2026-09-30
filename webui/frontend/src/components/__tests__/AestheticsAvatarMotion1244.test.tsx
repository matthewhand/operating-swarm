/**
 * #1244 — the operator-facing opt-in lives in Settings → Aesthetics. It must
 * persist and mirror onto the root `data-avatar-motion` attribute the CSS
 * reduced-motion gate reads.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ToastProvider } from '../DaisyUI'
import { AestheticsPane } from '../settings/panes/AestheticsPane'
import {
  AVATAR_MOTION_ATTRIBUTE,
  AVATAR_MOTION_STORAGE_KEY,
} from '../../lib/motionPreference'

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

describe('#1244: Aesthetics avatar-motion opt-in', () => {
  afterEach(() => {
    localStorage.removeItem(AVATAR_MOTION_STORAGE_KEY)
    document.documentElement.removeAttribute(AVATAR_MOTION_ATTRIBUTE)
    vi.unstubAllGlobals()
  })

  it('toggles on: persists and mirrors onto <html>', () => {
    stubFetch()
    renderPane()
    const toggle = screen.getByTestId('avatar-motion-toggle') as HTMLInputElement
    expect(toggle.checked).toBe(false)

    fireEvent.click(toggle)

    expect(localStorage.getItem(AVATAR_MOTION_STORAGE_KEY)).toBe('always')
    expect(document.documentElement).toHaveAttribute(AVATAR_MOTION_ATTRIBUTE, 'always')
    expect((screen.getByTestId('avatar-motion-toggle') as HTMLInputElement).checked).toBe(true)
  })

  it('toggles off: reverts to system and clears the attribute', () => {
    localStorage.setItem(AVATAR_MOTION_STORAGE_KEY, 'always')
    document.documentElement.setAttribute(AVATAR_MOTION_ATTRIBUTE, 'always')
    stubFetch()
    renderPane()
    const toggle = screen.getByTestId('avatar-motion-toggle') as HTMLInputElement
    expect(toggle.checked).toBe(true)

    fireEvent.click(toggle)

    expect(localStorage.getItem(AVATAR_MOTION_STORAGE_KEY)).toBe('system')
    expect(document.documentElement).not.toHaveAttribute(AVATAR_MOTION_ATTRIBUTE)
  })
})
