/**
 * #1801 — the CLI agent settings icon is invisible but still hit-testable on a
 * desktop pointer.
 *
 * `.os-cli-settings-btn` is a separate control from the chat pill's
 * `.os-agent-pill__action`. The equivalent two-rule fix had already landed for
 * the pill and was never extended here, so on `(hover: hover) and
 * (pointer: fine)` the button faded to `opacity: 0` while staying fully
 * clickable: a pointer aimed at the row's empty right edge landed on an
 * invisible control instead of the row underneath.
 *
 * These read the PARSED rules out of `src/index.css` rather than grepping it.
 * A bare `expect(css).toContain('pointer-events: none')` would be satisfied by
 * the six-line-later pill rule, by a comment quoting this very sentence, or by
 * any of the sheet's other `pointer-events` declarations — and it would break
 * on a reformat. `declarationIn` brace-matches the media block, then
 * whole-compound-matches the nested selector, and `declarations()` strips
 * comments, so only a real declaration under the real selector counts.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import CliAgentsSettingsPane from '../CliAgentsSettingsPane'
import { ToastProvider } from '../DaisyUI'
import {
  declaration,
  declarationIn,
  readCssSource,
  ruleBodies,
} from '../../lib/__tests__/helpers/cssRules'

const css = readCssSource()
/** The desktop-pointer gate. Touch devices never match it, so they are unaffected. */
const HOVER_FINE = '@media (hover: hover) and (pointer: fine)'
/** The at-rest rule inside it: hidden, therefore must not be hit-testable. */
const AT_REST = '.os-cli-agent-row .os-cli-settings-btn'
/** Every selector that reveals it again. Each must restore hit-testing too. */
const REVEALED = [
  '.os-cli-agent-row:hover .os-cli-settings-btn',
  '.os-cli-agent-row:focus-within .os-cli-settings-btn',
  '.os-cli-agent-row .os-cli-settings-btn:focus',
  '.os-cli-agent-row .os-cli-settings-btn[aria-expanded="true"]',
]

const KNOWN = ['claude']

function stubFetch(config: Record<string, { cmd?: string[] }>) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method || 'GET'
      if (url.includes('/v1/config/sections/cli_agents') && method === 'PATCH') {
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'config_section', data: config }),
        } as Response
      }
      if (url.includes('/v1/config/sections/cli_agents')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'config_section', data: config }),
        } as Response
      }
      if (url.includes('/v1/cli-agents')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            clis: KNOWN,
            known: KNOWN,
            configured: Object.keys(config),
            discovered: [],
            installed: [],
            suggestions: {},
            native_consensus: {},
            catalog: {},
          }),
        } as Response
      }
      if (url.includes('/v1/rate-limits')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'provider_rate_limits', data: [] }),
        } as Response
      }
      return { ok: true, status: 200, json: async () => ({}) } as Response
    }),
  )
}

function renderPane() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <CliAgentsSettingsPane />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('#1801 the hidden CLI settings button stops intercepting clicks', () => {
  beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      writable: true,
      value: vi.fn(),
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  /* Part 1 — the parsed-CSS assertions. These are the ones that catch the bug:
     on today's sheet `pointer-events` is simply absent from both rules. */
  it('takes the at-rest rule out of the hit-test tree on a desktop pointer', () => {
    // Non-vacuity: the media block really does carry this rule, and really does
    // hide it. If `declarationIn` stopped reaching inside the block, or the rule
    // were renamed away, this fails instead of the next line passing on nothing.
    expect(ruleBodies(css, AT_REST).length, `${AT_REST} must exist in index.css`).toBeGreaterThan(0)
    expect(
      declarationIn(css, AT_REST, 'opacity', HOVER_FINE),
      `${AT_REST} inside ${HOVER_FINE} must set opacity`,
    ).toBe('0')

    expect(
      declarationIn(css, AT_REST, 'pointer-events', HOVER_FINE),
      `${AT_REST} at opacity: 0 must be pointer-events: none, or an invisible button eats clicks meant for the row`,
    ).toBe('none')
  })

  it.each(REVEALED)(
    'restores pointer-events: auto on %s',
    (selector) => {
      expect(
        declarationIn(css, selector, 'opacity', HOVER_FINE),
        `${selector} inside ${HOVER_FINE} must set opacity`,
      ).toBe('1')
      expect(
        declarationIn(css, selector, 'pointer-events', HOVER_FINE),
        `${selector} must be pointer-events: auto — dropping it strands keyboard users on :focus-within and makes an open popover unclickable`,
      ).toBe('auto')
    },
  )

  /* The accessibility asymmetry: the BASE rule is the touch-device path, where
     the control is deliberately always visible and always clickable. Putting
     `pointer-events: none` there would break touch outright. */
  it('leaves the touch-device base rule visible and hit-testable', () => {
    expect(declaration(css, '.os-cli-settings-btn', 'opacity')).toBe('1')
    expect(
      declaration(css, '.os-cli-settings-btn', 'pointer-events'),
      'the base rule must not disable hit-testing — it is the always-on touch path',
    ).toBeUndefined()
  })

  /* Part 2 — non-vacuity at the DOM level. jsdom cannot evaluate the media
     query, so this does NOT pretend to prove the desktop behaviour. What it
     does prove is that the selectors part 1 asserts on describe real, mounted,
     reachable elements: a typo'd selector matching nothing in the sheet cannot
     be paired with a live control here. */
  it('mounts a live settings button inside the row the selectors describe', async () => {
    stubFetch({ claude: { cmd: ['claude', '-p', '{prompt}'] } })
    renderPane()

    const row = await screen.findByTestId('cli-row-claude')
    expect(row).toHaveClass('os-cli-agent-row')

    const button = screen.getByRole('button', { name: 'Settings for claude' })
    expect(button).toHaveClass('os-cli-settings-btn')
    // The at-rest selector is a DESCENDANT of `.os-cli-agent-row`, so the
    // button has to be inside one for the parsed rule to mean anything.
    expect(button.closest('.os-cli-agent-row')).toBe(row)

    // Reachable: the click that #1801 was eating is the one that opens the pane.
    expect(button).not.toBeDisabled()
    fireEvent.click(button)
    expect(await screen.findByRole('dialog', { name: 'claude settings' })).toBeInTheDocument()
    expect(button).toHaveAttribute('aria-expanded', 'true')
  })
})
