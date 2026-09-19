/**
 * #676 UI — Settings → Aesthetics renders an "Apply to all (N)" button next
 * to the bubble-theme picker: disabled with a hint when no differing
 * overrides exist, enabled when they do, and clicking it clears them.
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '../DaisyUI'
import { setAgentBubbleTheme } from '../../lib/bubbleTheme'

describe('#676 Apply to all (Settings → Aesthetics)', () => {
  beforeEach(() => localStorage.clear())

  async function renderPane() {
    const mod = await import('../SettingsSheet')
    const SettingsSheet = mod.default
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    return render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <SettingsSheet isOpen initialSection="aesthetics" onClose={() => {}} />
        </ToastProvider>
      </QueryClientProvider>,
    )
  }

  it('disabled with a hint when no overrides exist', async () => {
    await renderPane()
    const btn = await screen.findByTestId('aesthetics-apply-all')
    expect(btn).toHaveAttribute('disabled')
    expect(screen.getByTestId('aesthetics-apply-all-hint')).toHaveTextContent(
      /every agent already follows the default/i,
    )
  })

  it('enabled with a count when overrides differ, and clicking clears them', async () => {
    setAgentBubbleTheme('codey', 'irc')
    setAgentBubbleTheme('zeus', 'feed')
    await renderPane()
    const btn = await screen.findByTestId('aesthetics-apply-all')
    expect(btn).not.toHaveAttribute('disabled')
    expect(btn).toHaveTextContent(/2/i)
    fireEvent.click(btn)
    expect(btn).toHaveAttribute('disabled')
    const { agentBubbleThemeOverrides } = await import('../../lib/bubbleTheme')
    expect(agentBubbleThemeOverrides()).toEqual({})
  })
})
