import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { OPEN_SETTINGS_EVENT } from '../SettingsSheet'
import { SUPPORT_ACTION_CHIPS, SupportActionChips, SupportBriefingPill } from '../SupportBriefingPill'
import { SPA_SETTINGS_INFERENCE_HREF } from '../../lib/settingsLinks'

describe('SupportActionChips #1442', () => {
  const opened: unknown[] = []
  const listener = (event: Event) => opened.push((event as CustomEvent).detail)

  beforeEach(() => {
    opened.length = 0
    window.addEventListener(OPEN_SETTINGS_EVENT, listener)
  })

  afterEach(() => {
    window.removeEventListener(OPEN_SETTINGS_EVENT, listener)
  })

  it('Set inference is a SPA deeplink, not the Django dump', () => {
    const inference = SUPPORT_ACTION_CHIPS.find((chip) => chip.label === 'Set inference')
    expect(inference?.href).toBe(SPA_SETTINGS_INFERENCE_HREF)
    expect(inference?.href).not.toBe('/settings/')
  })

  it('clicking Set inference opens the LLM profiles sheet without navigation', () => {
    render(<SupportActionChips />)
    const link = screen.getByRole('link', { name: 'Set inference' })
    expect(link).toHaveAttribute('href', SPA_SETTINGS_INFERENCE_HREF)
    fireEvent.click(link)
    expect(opened).toEqual([{ section: 'llm-profiles' }])
  })

  it('briefing markdown Settings links open the sheet', () => {
    render(
      <SupportBriefingPill briefing="Open [Settings](/chat?settings=llm-profiles)." />,
    )
    fireEvent.click(screen.getByRole('button', { name: /System → Support/i }))
    fireEvent.click(screen.getByRole('link', { name: 'Settings' }))
    expect(opened).toEqual([{ section: 'llm-profiles' }])
  })
})
