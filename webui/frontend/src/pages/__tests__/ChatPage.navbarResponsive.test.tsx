import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ToastProvider } from '../../components/DaisyUI'
import { RailChromeProvider } from '../../components/RailChrome'
import ChatPage from '../ChatPage'
import { declarations, rule } from '../../lib/__tests__/helpers/cssRules'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  url: string
  readyState = 0
  onopen: ((e?: unknown) => void) | null = null
  onclose: ((e?: unknown) => void) | null = null
  onmessage: ((e: MessageEvent) => void) | null = null
  send = vi.fn()
  close = vi.fn()

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  open() {
    this.readyState = 1
    this.onopen?.()
  }
}

const CLI_RAIL = [
  {
    id: 'cli_agent',
    object: 'cli.agent',
    name: 'cli_agent',
    cli: 'grok',
    kind: 'cli',
    description: 'Host CLI',
    installed: true,
  },
]

const PROFILES = {
  object: 'llm_profiles',
  profiles: [
    { id: 'orchestration', object: 'llm_profile', source: 'test', owned_by: 'test', name: 'Orchestration' },
  ],
  default_llm_profile: 'orchestration',
  default_is_auto: false,
  override_per_task: false,
  task_llm_profiles: {},
  auto_picks: {},
  aliases_used: [],
  warnings: [],
  routes: {},
  task_classes: ['orchestration'],
}

function stubGlobals() {
  MockWebSocket.instances = []
  Element.prototype.scrollIntoView = vi.fn()
  vi.stubGlobal('WebSocket', MockWebSocket)
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/v1/llm-profiles')) {
        return { ok: true, status: 200, json: async () => PROFILES } as Response
      }
      if (url.includes('/v1/cli-agents')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            clis: ['grok'],
            known: ['grok'],
            configured: ['grok'],
            discovered: ['grok'],
            installed: ['grok'],
            suggestions: {},
            default_cli: 'grok',
            native_consensus: {},
            catalog: {},
            list_models: {},
            rail: CLI_RAIL,
          }),
        } as Response
      }
      return {
        ok: true,
        json: async () => ({ results: [], data: [], messages: [] }),
      } as Response
    }),
  )
}

function renderChat(entry: string, narrow = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <RailChromeProvider
          value={{
            narrow,
            railOpen: false,
            openRail: () => undefined,
            closeRail: () => undefined,
          }}
        >
          <MemoryRouter initialEntries={[entry]}>
            <ChatPage />
          </MemoryRouter>
        </RailChromeProvider>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('REQ-865: responsive navbar element prioritization (#255)', () => {
  beforeEach(() => {
    localStorage.clear()
    // #847: the toggle defaults to 'if_not_system' and the suite runs on the
    // system theme — these tests assert the toggle is present, so force it on.
    localStorage.setItem('swarm_theme_navbar_mode', 'always')
    stubGlobals()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('keeps expanders, controls, and avatar visible while the name fades', async () => {
    renderChat('/chat?blueprint=support', true)
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const header = screen.getByRole('banner')
    expect(header).toHaveClass('os-chat-header')
    // #445: the header clips nothing — the routing flyout is an absolutely
    // positioned child of the picker inside it, and `overflow-hidden` cut every
    // row but the first. REQ-865's requirement (the name fades while the
    // expanders, controls, and avatar keep their place) is asserted on those
    // elements below, which is where it is enforced.
    expect(header).not.toHaveClass('overflow-hidden')
    expect(header).toHaveClass('gap-1.5')
    expect(header).toHaveClass('sm:gap-3')

    const expander = screen.getByRole('button', { name: 'Open agent list' })
    expect(expander).toHaveClass('shrink-0')
    expect(header).toContainElement(expander)

    const identity = header.querySelector('.os-chat-header__identity')
    expect(identity).toHaveClass('min-w-0')
    expect(identity).toHaveClass('flex-1')

    const card = screen.getByTestId('selected-agent-header')
    const avatarBtn = screen.getByTestId('header-avatar-generations')
    expect(avatarBtn).toHaveClass('shrink-0')
    expect(card).toContainElement(avatarBtn)
    expect(card.querySelector('.os-chat-header__avatar')).toBeTruthy()

    const title = card.querySelector('h1')
    expect(title).toHaveClass('os-navbar-identity-label')
    expect(title).toHaveClass('min-w-0')
    // #1715 replaced `flex-1` with `w-full` here, and the old `toHaveClass(
    // 'flex-1')` assertion is what went red with it (a pre-existing break on
    // main, not a regression from this work). `flex-1` was a proxy for two
    // properties — "the label may shrink" and "the label fills the card" — and
    // #1715 could only keep the second by dropping the utility, because
    // `flex-grow: 1` on the column main axis stretched the lone label into a
    // box whose text sat top-biased. So the proxy is replaced by the two
    // properties themselves, read from the rule that actually sets them:
    // `flex: 0 1 auto` is shrink-1/grow-0 and `width: 100%` fills. A test that
    // only checked the class could not see either number, and a test that only
    // checked the class would pass again the moment someone re-added `flex-1`.
    // eslint-disable-next-line testing-library/no-node-access -- the label's resolved flex behaviour is the claim
    const labelRule = declarations(
      rule(
        readFileSync(resolve(process.cwd(), 'src/index.css'), 'utf8'),
        '.os-navbar-identity-card .os-navbar-identity-label',
      ),
    )
    expect(labelRule.flex).toBe('0 1 auto')
    expect(labelRule.width).toBe('100%')
    expect(title).toHaveClass('w-full')
    expect(title).not.toHaveClass('truncate')

    const controls = header.querySelector('.os-chat-header__controls')
    expect(controls).toBeTruthy()
    expect(controls).toHaveClass('shrink-0')
    expect(controls).toHaveClass('gap-1')
    expect(controls).toHaveClass('sm:gap-2')

    expect(await screen.findByTestId('navbar-routing-picker')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Computer control' })).toBeInTheDocument()
    expect(screen.getByTestId('theme-toggle-btn')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open settings' })).toHaveClass('shrink-0')

    // #773: no navbar token meter — the composer badge is the one meter.
    expect(screen.queryByTestId('token-meter-button')).toBeNull()

    // #1704 moved the unset-folder affordance out of `.os-navbar-identity-text`
    // into the new `.os-agent-pill__actions` cluster and gave that button the
    // `os-navbar-edit-btn` class too, placing it BEFORE the pencil. The old
    // positional `card.querySelector('.os-navbar-edit-btn')` therefore began
    // returning the FOLDER button -- whose wrapper is a bare `shrink-0` and is
    // deliberately visible at every width -- so this assertion silently
    // changed subject and failed. The pencil is the control REQ-865 is about
    // (it is the one deprioritised below `sm`), so select it by its accessible
    // name rather than by position, scoped to the card.
    const pencil = within(card).getByRole('button', { name: 'Edit agent' })
    const pencilWrap = pencil.parentElement
    expect(pencilWrap).toHaveClass('hidden')
    expect(pencilWrap).toHaveClass('sm:flex')
    // Stronger than the old lookup: pin WHICH wrapper this is, so re-ordering
    // or adding a third edit control cannot retarget the assertion again.
    expect(pencilWrap).toHaveAttribute('data-tip', 'Edit agent')
    // #1713: the folder affordance that used to shadow the pencil is NOT
    // offered on this seat. `support` resolves to an API seat, and an API
    // seat's editor destination renders a "Coming soon" stub instead of a
    // folder control — so the button here was a dead end. It used to be
    // asserted present on this very seat, which is the bug.
    //
    // The control is still covered where it belongs: `ChatHeader.folderPill1704
    // .test.tsx` renders the cluster directly, and
    // `ChatPage.1713FolderGate.test.tsx` asserts the offer/destination pair
    // through the real page on both a CLI and an API seat.
    expect(within(card).queryByRole('button', { name: 'Select folder' })).toBeNull()
  })

  it('does not render the rail expander on a wide viewport', async () => {
    renderChat('/chat?blueprint=support', false)
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(screen.queryByRole('button', { name: 'Open agent list' })).not.toBeInTheDocument()
  })

  it('mounts CLI routing picker in the composer, and session switcher in the navbar controls cluster', async () => {
    renderChat('/chat?blueprint=cli_agent&mode=cli&cli=grok', true)
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const header = screen.getByRole('banner')
    const controls = header.querySelector('.os-chat-header__controls')
    expect(controls).toHaveClass('shrink-0')

    const composer = screen.getByRole('textbox', { name: 'Chat message' }).closest('.os-composer')
    const cliPicker = await screen.findByTestId('navbar-routing-picker')
    expect(cliPicker).toHaveAttribute('data-seat-kind', 'cli')
    expect(composer).toContainElement(cliPicker)

    const sessionSwitcher = await screen.findByTestId('os-cli-session-switcher')
    expect(controls).toContainElement(sessionSwitcher)
    expect(screen.getByRole('button', { name: 'Computer control' })).toBeInTheDocument()
    expect(screen.getByTestId('theme-toggle-btn')).toBeInTheDocument()
  })

  it('defines the identity fade mask in index.css', () => {
    const css = readFileSync(resolve(process.cwd(), 'src/index.css'), 'utf8')
    expect(css).toContain('.os-navbar-identity-label')
    expect(css).toContain(
      'mask-image: linear-gradient(to right, black calc(100% - 1.5rem), transparent 100%)',
    )
    expect(css).toContain('-webkit-mask-image: linear-gradient(to right, black calc(100% - 1.5rem), transparent 100%)')
    expect(css).toContain('flex-wrap: nowrap')
    expect(css).toContain('.os-chat-header__controls')
  })
})
