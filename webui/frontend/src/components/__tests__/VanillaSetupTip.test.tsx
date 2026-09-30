/**
 * #1700 (2) / (3) — the tip's call to action must be actionable, and its
 * dismissal must be reachable.
 *
 * The load-bearing assertion is the CTA one: it is a real `<a href>` to a
 * `/chat?settings=…` deep link, and `lib/settingsLinks.ts`'s own parser accepts
 * it. A `<button onClick>` would pass a "click me" test and still be a dead end
 * in a chat transcript (no middle-click, no copy-address, no keyboard), and a
 * link the settings parser rejects would be a link that reloads the page.
 *
 * Fixtures come from `firstVanillaTip`, never hand-written, so this file cannot
 * pass against a `VanillaTip` shape the policy no longer produces.
 */

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { VanillaSetupTip } from '../VanillaSetupTip'
import { parseSettingsHref } from '../../lib/settingsLinks'
import { CONFIGURE_API_TIP_ID, firstVanillaTip } from '../../lib/vanillaTips'

afterEach(cleanup)

const apiTip = firstVanillaTip({
  supportContext: {
    object: 'support.context',
    agents: [],
    agent_count: 0,
    inference: {
      configured: false,
      profiles: [],
      env_signals: [],
      quickstart: { doc: '', anchor: '', settings: '', profiles: '', cli: '' },
    },
    create: {},
  },
})

describe('VanillaSetupTip', () => {
  it('the policy produced the tip this file renders', () => {
    // If that ever stops being true, every assertion below is testing a shape
    // no code path emits any more.
    expect(apiTip).not.toBeNull()
    expect(apiTip?.id).toBe(CONFIGURE_API_TIP_ID)
  })

  it('renders the title and body the policy decided on', () => {
    render(<VanillaSetupTip tip={apiTip!} onDismiss={() => {}} />)
    expect(screen.getByText(apiTip!.title)).toBeTruthy()
    expect(screen.getByText(apiTip!.body)).toBeTruthy()
  })

  it('identifies which tip it is, so the page and its tests can tell them apart', () => {
    render(<VanillaSetupTip tip={apiTip!} onDismiss={() => {}} />)
    expect(screen.getByTestId('vanilla-setup-tip').getAttribute('data-tip-id')).toBe(
      CONFIGURE_API_TIP_ID,
    )
  })

  it('the CTA is a link the SPA settings parser accepts', () => {
    render(<VanillaSetupTip tip={apiTip!} onDismiss={() => {}} />)
    const cta = screen.getByTestId('vanilla-tip-cta') as HTMLAnchorElement
    expect(cta.tagName).toBe('A')
    expect(cta.getAttribute('href')).toBe(apiTip!.cta.href)
    // The real contract: the in-app handler opens the right Settings pane.
    expect(parseSettingsHref(cta.getAttribute('href'))).toBe('llm-profiles')
    expect(screen.getByText(apiTip!.cta.label)).toBeTruthy()
  })

  it('the tip is announced politely, never as an interrupting alert', () => {
    render(<VanillaSetupTip tip={apiTip!} onDismiss={() => {}} />)
    const alert = screen.getByRole('status')
    expect(alert.getAttribute('role')).toBe('status')
  })

  it('dismissing calls back once, so the caller can persist the right id', () => {
    const onDismiss = vi.fn()
    render(<VanillaSetupTip tip={apiTip!} onDismiss={onDismiss} />)
    screen.getByTestId('vanilla-tip-dismiss').click()
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('the dismiss control names the tip it dismisses', () => {
    render(<VanillaSetupTip tip={apiTip!} onDismiss={() => {}} />)
    expect(screen.getByLabelText(`Dismiss: ${apiTip!.title}`)).toBeTruthy()
  })

  it('renders nothing to click when there is no tip to dismiss', () => {
    // The guard that keeps a `null` policy answer from rendering a hollow shell.
    const absent = firstVanillaTip({ supportContext: null })
    expect(absent).toBeNull()
    const { unmount } = render(
      <div>{absent ? <VanillaSetupTip tip={absent} onDismiss={() => {}} /> : null}</div>,
    )
    expect(screen.queryByTestId('vanilla-tip-dismiss')).toBeNull()
    unmount()
  })
})
