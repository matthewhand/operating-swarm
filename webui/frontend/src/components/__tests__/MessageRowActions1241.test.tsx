/**
 * #1241 — always-visible action rows are dimmed until hovered / focused /
 * activated. CSS owns the opacity; the component owns the hooks the CSS keys
 * off (`data-always-visible`, `data-activated`).
 */
import { afterEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ToastProvider } from '../DaisyUI'
import MessageRowActions from '../MessageRowActions'
import {
  ACTIONS_VISIBLE_STORAGE_KEY,
  saveActionsAlwaysVisible,
} from '../../lib/responsivePrefs'

function forceAlwaysVisible() {
  saveActionsAlwaysVisible({ mobile: true, tablet: true, desktop: true })
}

describe('#1241 always-visible action dimming', () => {
  afterEach(() => {
    localStorage.removeItem(ACTIONS_VISIBLE_STORAGE_KEY)
  })

  it('marks an always-visible row for CSS dimming without a competing utility', () => {
    forceAlwaysVisible()
    render(
      <ToastProvider>
        <MessageRowActions text="hello" />
      </ToastProvider>,
    )
    const row = screen.getByTestId('os-message-row-actions')
    expect(row).toHaveAttribute('data-always-visible', 'true')
    expect(row.className).toContain('os-actions-always-visible')
    // No Tailwind opacity utility should fight the CSS dimming rule.
    expect(row.className).not.toContain('opacity-100')
    // Reduced-motion is respected on the transition.
    expect(row.className).toContain('motion-reduce:transition-none')
    expect(row).not.toHaveAttribute('data-activated')
  })

  it('flags an activated row (expanded Thinking) for full brightness', () => {
    forceAlwaysVisible()
    render(
      <ToastProvider>
        <MessageRowActions
          text="hello"
          hasThinking
          onToggleThinking={() => {}}
          thinkingOpen
        />
      </ToastProvider>,
    )
    expect(screen.getByTestId('os-message-row-actions')).toHaveAttribute(
      'data-activated',
      'true',
    )
  })

  it('keeps the hover-reveal contract when not always visible', () => {
    localStorage.removeItem(ACTIONS_VISIBLE_STORAGE_KEY)
    render(
      <ToastProvider>
        <MessageRowActions text="hello" />
      </ToastProvider>,
    )
    const row = screen.getByTestId('os-message-row-actions')
    expect(row).not.toHaveAttribute('data-always-visible')
    expect(row.className).toContain('group-hover/osrow:md:opacity-100')
    expect(row.className).not.toContain('os-actions-always-visible')
  })
})
