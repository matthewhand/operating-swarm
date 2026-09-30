/**
 * #1700 (3) / #1703 / #1725 — the first-run tip is *mounted*, and the channel it
 * rides is the one the server already had.
 *
 * `lib/vanillaTips.test.ts` proves the policy; this file proves the wiring,
 * which is what #1725 is actually about. A policy with no consumer is the exact
 * defect shape: the facts existed (`GET /v1/support/context/` had **no SPA
 * consumer at all**), the function was correct, and the operator still saw
 * nothing. These assertions are on rendered DOM and on the requests the page
 * made.
 *
 * The load-bearing assertion here is the CROSS-SYSTEM one: two independent
 * first-run tips (#1703 host CLI, #1700 (3) no provider) share one slot above
 * the transcript, and no host state may ever put both on screen. Neither tip's
 * own test can catch that, because neither test renders the other.
 *
 * Covered here:
 *   * a greenfield host with no CLI renders the API tip at the top of the chat;
 *   * a greenfield host WITH a detected CLI renders the host-CLI tip and no
 *     second tip — with both conditions unmet;
 *   * a dismissal PATCHes `/v1/preferences/` and survives the next mount;
 *   * a configured provider renders no tip (never nag an operator twice);
 *   * the tip is not gated on the seat in the URL — ChatPage writes
 *     `?blueprint=support` as its default on every load, so such a gate would
 *     suppress the tip on the greenfield load it exists for.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
import { CONFIGURE_API_TIP_ID } from '../../lib/vanillaTips'
import { HOST_CLI_TIP_PREF_KEY } from '../../lib/hostCliTip'

type WsHandler = ((ev?: Event) => void) | null
class MockWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static instances: MockWebSocket[] = []
  readyState = MockWebSocket.CONNECTING
  onopen: WsHandler = null
  onmessage: WsHandler = null
  onclose: WsHandler = null
  send = vi.fn()
  close = vi.fn()
  constructor() {
    MockWebSocket.instances.push(this)
  }
  open() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }
}

interface HostFacts {
  inferenceConfigured: boolean
  discovered: string[]
  defaultLlmReady?: boolean
}

const prefPatches: unknown[] = []

function stubFetch(host: HostFacts) {
  const configured: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
      const url = String(input)
      if (init?.method === 'PATCH' && url.includes('/v1/preferences/')) {
        prefPatches.push(JSON.parse(String(init.body ?? '{}')))
        return { ok: true, status: 200, json: async () => ({}) } as Response
      }
      if (url.includes('/v1/preferences/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'user_preferences',
            principal: 'p',
            guest: false,
            empty: true,
            values: {},
          }),
        } as Response
      }
      if (url.includes('/v1/support/context/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'support.context',
            agent_count: 0,
            agents: [],
            inference: {
              configured: host.inferenceConfigured,
              profiles: host.inferenceConfigured ? ['default'] : [],
              env_signals: [],
              quickstart: { doc: '', anchor: '', settings: '', profiles: '', cli: '' },
            },
            create: {},
          }),
        } as Response
      }
      if (url.includes('/v1/cli-agents/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'cli_agents',
            clis: host.discovered,
            known: host.discovered,
            configured,
            discovered: host.discovered,
            installed: host.discovered,
            suggestions: Object.fromEntries(host.discovered.map((n) => [n, { cmd: [n] }])),
            rail: [],
            seat_capabilities: {},
          }),
        } as Response
      }
      if (url.includes('/v1/llm-profiles/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'llm_profiles',
            profiles: [],
            default_llm_profile: 'default',
            default_llm_ready: host.defaultLlmReady ?? true,
          }),
        } as Response
      }
      if (url.includes('/v1/blueprints/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'list',
            data: [{ id: 'support', object: 'blueprint', name: 'Support', description: '', seat_listed: true, chat_ready: true, manage_links: [] }],
          }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response
    }),
  )
}

function renderChat(entry: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[entry]}>
          <ChatPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

const GREENFIELD_NO_CLI: HostFacts = { inferenceConfigured: false, discovered: [] }
const GREENFIELD_WITH_CLI: HostFacts = { inferenceConfigured: false, discovered: ['opencode'] }
const WIRED: HostFacts = { inferenceConfigured: true, discovered: [] }
const WIRED_WITH_UNWIRED_CLI: HostFacts = {
  inferenceConfigured: true,
  discovered: ['opencode'],
}

beforeEach(() => {
  MockWebSocket.instances = []
  window.localStorage.clear()
  prefPatches.length = 0
  Element.prototype.scrollIntoView = vi.fn()
  vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
})

afterEach(() => {
  vi.unstubAllGlobals()
  window.localStorage.clear()
  resetConversationThreads()
})

async function open(entry = '/chat') {
  renderChat(entry)
  await act(async () => {
    MockWebSocket.instances[0]?.open()
  })
}

/** Every first-run tip on screen, whichever module rendered it. */
function firstRunTips(): HTMLElement[] {
  return [
    ...document.querySelectorAll<HTMLElement>('[data-testid="vanilla-setup-tip"]'),
    ...document.querySelectorAll<HTMLElement>('[data-testid="host-cli-tip"]'),
  ]
}

describe('#1700 (3) — no provider configured', () => {
  it('renders the API tip at the top of the chat, with an actionable CTA', async () => {
    stubFetch(GREENFIELD_NO_CLI)
    await open()
    const tip = await screen.findByTestId('vanilla-setup-tip')
    expect(tip.getAttribute('data-tip-id')).toBe(CONFIGURE_API_TIP_ID)
    const cta = screen.getByTestId('vanilla-tip-cta')
    expect(cta.getAttribute('href')).toBe('/chat?settings=llm-profiles')
    expect(cta.textContent).toContain('Set up an API provider')
  })

  it('renders nothing once a provider is configured', async () => {
    // Never tell an operator to do something they already did.
    stubFetch(WIRED)
    await open()
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(screen.queryByTestId('vanilla-setup-tip')).toBeNull()
  })
})

describe('at most one first-run tip, whichever module renders it', () => {
  it('a detected CLI takes the slot, and the API tip is not stacked beneath it', async () => {
    // BOTH conditions hold: no provider, and a CLI on PATH that is not wired up.
    // The host-CLI tip is the one rendered, because wiring a CLI needs no key.
    // A regression that dropped the stand-down would put two tips on screen and
    // this is the only assertion that can see it.
    stubFetch(GREENFIELD_WITH_CLI)
    await open()
    const cliTip = await screen.findByTestId('host-cli-tip')
    expect(cliTip.getAttribute('data-cli')).toBe('opencode')
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(firstRunTips()).toHaveLength(1)
    expect(screen.queryByTestId('vanilla-setup-tip')).toBeNull()
  })

  it('a configured provider with an unwired CLI still shows only the CLI tip', async () => {
    stubFetch(WIRED_WITH_UNWIRED_CLI)
    await open()
    await screen.findByTestId('host-cli-tip')
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(firstRunTips()).toHaveLength(1)
    expect(screen.queryByTestId('vanilla-setup-tip')).toBeNull()
  })

  it('no CLI and a configured provider means no first-run tip at all', async () => {
    stubFetch({ inferenceConfigured: true, discovered: [] })
    await open()
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(firstRunTips()).toHaveLength(0)
  })
})

describe('dismissal is persisted, not component state', () => {
  it('clicking dismiss PATCHes /v1/preferences/ and hides the tip', async () => {
    stubFetch(GREENFIELD_NO_CLI)
    await open()
    await screen.findByTestId('vanilla-setup-tip')
    const button = screen.getByTestId('vanilla-tip-dismiss')
    await act(async () => {
      button.click()
    })
    await waitFor(() => {
      expect(prefPatches.length).toBeGreaterThan(0)
    })
    expect(prefPatches).toContainEqual({
      values: { vanilla_tip_configure_api_dismissed: true },
    })
    await waitFor(() => {
      expect(screen.queryByTestId('vanilla-setup-tip')).toBeNull()
    })
  })

  it('a dismissal already in localStorage suppresses the tip on the next mount', async () => {
    // The reload case, without a reload: a fresh render reads the same store a
    // dismiss wrote to. Component state alone would not survive this.
    window.localStorage.setItem('swarm_vanilla_tip_dismissed_configure-api', '1')
    stubFetch(GREENFIELD_NO_CLI)
    await open()
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(screen.queryByTestId('vanilla-setup-tip')).toBeNull()
  })

  it('the API tip dismissal does not silence the host-CLI tip', async () => {
    // Two conditions, two keys. A shared key would make the second assertion
    // here fail after a user dismissed the first — silently, days later.
    window.localStorage.setItem('swarm_vanilla_tip_dismissed_configure-api', '1')
    stubFetch(GREENFIELD_WITH_CLI)
    await open()
    await screen.findByTestId('host-cli-tip')
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(firstRunTips()).toHaveLength(1)
    expect(screen.getByTestId('host-cli-tip')).toBeTruthy()
  })

  it('the host-CLI tip dismissal key is the one it writes', async () => {
    stubFetch(WIRED_WITH_UNWIRED_CLI)
    await open()
    await screen.findByTestId('host-cli-tip')
    await act(async () => {
      screen.getByTestId('host-cli-tip-never').click()
    })
    await waitFor(() => {
      expect(prefPatches).toContainEqual({ values: { [HOST_CLI_TIP_PREF_KEY]: true } })
    })
  })
})

describe('the tip survives ChatPage selecting a default seat', () => {
  it('still renders when the page has written ?blueprint=support', async () => {
    // ChatPage selects a default seat a moment after mount, so the URL always
    // carries one. Gating the tip on "did the operator ask for a seat?" would
    // therefore suppress it on every load — including the greenfield load it
    // exists for. This pins that the tip is not URL-gated.
    stubFetch(GREENFIELD_NO_CLI)
    await open()
    const tip = await screen.findByTestId('vanilla-setup-tip')
    expect(tip.getAttribute('data-tip-id')).toBe(CONFIGURE_API_TIP_ID)
    expect(window.location.search).not.toContain('blueprint')
  })

  it('and renders on a deep link, where the next turn is what would fail', async () => {
    stubFetch(GREENFIELD_NO_CLI)
    await open('/chat?blueprint=support')
    const tip = await screen.findByTestId('vanilla-setup-tip')
    expect(tip.getAttribute('data-tip-id')).toBe(CONFIGURE_API_TIP_ID)
  })
})
