import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import RateLimitStatusLine from '../RateLimitStatusLine'
import { settingsTargetForProvider } from '../../lib/providerRateLimits'

const openSettingsSheet = vi.fn()

vi.mock('../settings/kernel', () => ({
  openSettingsSheet: (...args: unknown[]) => openSettingsSheet(...args),
}))

describe('RateLimitStatusLine', () => {
  it('is info chrome (not a model bubble) and opens that provider’s fields', () => {
    const wait = {
      reason: 'messages_per_minute' as const,
      remaining_seconds: 11,
      provider: 'cli:stub',
      wait_until_ms: Date.now() + 11_000,
      settings: settingsTargetForProvider('cli:stub'),
    }
    render(<RateLimitStatusLine wait={wait} nowMs={Date.now()} />)
    const line = screen.getByTestId('chat-status-rate-limit')
    expect(line.textContent).toMatch(/Waiting for stub/)
    expect(line.textContent).toMatch(/messages per minute/)
    expect(line.className).toMatch(/os-chat-status/)
    expect(line.className).not.toMatch(/chat-start|chat-end/)
    expect(line.textContent).not.toMatch(/Django/i)
    fireEvent.click(line)
    expect(openSettingsSheet).toHaveBeenCalledWith({
      section: 'cli-agents',
      providerId: 'cli:stub',
      focusRateLimits: true,
    })
  })
})
