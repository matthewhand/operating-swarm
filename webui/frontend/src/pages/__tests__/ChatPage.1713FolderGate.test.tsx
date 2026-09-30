/**
 * #1713 — the "Select folder" offer, and the destination it opens.
 *
 * `SelectFolderDeadEnd1713.test.tsx` proves the editor destination has a folder
 * control for a CLI seat and only a CLI seat. This file proves the *page* offers
 * the control on exactly that basis, by rendering the real `ChatPage` and asking
 * the DOM. Together the two pin the pair: the offer and the destination are
 * gated by the same fact, so neither can move without the other failing.
 *
 * The failure this replaces: an API seat was offered a "Select folder" button
 * whose destination rendered an explicit "Coming soon" stub — a control that
 * looked actionable and did nothing.
 *
 * `workspaceFolderEditable` is asserted separately, and it is deliberately
 * WIDER. It feeds `AgentConfigSidepane`'s own free-text "Working folder" input,
 * which works for an API agent and whose value the navbar subtitle reads back.
 * Narrowing that flag instead of splitting the two consumers would have deleted
 * a working feature; the test below is what makes that failure loud.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'

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

function blueprint(id: string, name: string, kind: string) {
  return {
    id,
    object: 'blueprint',
    name,
    description: '',
    kind,
    seat_listed: true,
    chat_ready: true,
    manage_links: [],
  }
}

function stubFetch(blueprints: unknown[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
      const url = String(input)
      if (init?.method === 'PATCH' && url.includes('/v1/preferences/')) {
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
      if (url.includes('/v1/blueprints/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'list', data: blueprints }),
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
            // Configured, so the first-run tip never appears and cannot be
            // mistaken for the control under test.
            inference: {
              configured: true,
              profiles: ['default'],
              env_signals: [],
              quickstart: { doc: '', anchor: '', settings: '', profiles: '', cli: '' },
            },
            create: {},
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
            default_llm_ready: true,
          }),
        } as Response
      }
      if (url.includes('/v1/cli-agents/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'cli_agents',
            clis: [],
            known: [],
            configured: [],
            discovered: [],
            installed: [],
            suggestions: {},
            rail: [],
            seat_capabilities: {},
          }),
        } as Response
      }
      return { ok: true, status: 200, json: async () => ({ data: [] }) } as Response
    }),
  )
}

// Seat identity is the blueprint ID convention the page itself reads
// (`lib/cliAgentContext.ts`: `cli_*` is a CLI seat, `api_*` an API seat), not a
// field on the payload, so these ids are the real switch.
const CLI_SEAT = [blueprint('cli_codey', 'Codey', 'cli')]
const API_SEAT = [blueprint('api_codey', 'Codey', 'api')]

async function open(entry: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[entry]}>
          <ChatPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
  await act(async () => {
    MockWebSocket.instances[0]?.open()
  })
}

function folderControl() {
  return screen.queryByTestId('os-navbar-workspace-subtitle-unset')
}

beforeEach(() => {
  MockWebSocket.instances = []
  window.localStorage.clear()
  Element.prototype.scrollIntoView = vi.fn()
  vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
})

afterEach(() => {
  vi.unstubAllGlobals()
  window.localStorage.clear()
  resetConversationThreads()
})

describe('#1713 the offer matches the destination', () => {
  it('a CLI seat — whose editor has a folder control — is offered one', async () => {
    stubFetch(CLI_SEAT)
    await open('/chat?blueprint=cli_codey')
    await waitFor(() => {
      expect(folderControl()).not.toBeNull()
    })
  })

  it('an API seat is NOT offered one, because its editor has none', async () => {
    // This is the dead end. Before the fix the control rendered here and its
    // destination answered "Coming soon".
    stubFetch(API_SEAT)
    await open('/chat?blueprint=api_codey')
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(folderControl()).toBeNull()
  })

  it('the gate is the seat, not a delayed render', async () => {
    // A control that appears a moment later would be a race, not a gate. The
    // negative case is held across a settle, not sampled once.
    stubFetch(API_SEAT)
    await open('/chat?blueprint=api_codey')
    await waitFor(() => {
      expect(document.querySelector('[data-testid="selected-agent-header"]')).not.toBeNull()
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50))
    })
    expect(folderControl()).toBeNull()
  })
})

describe('#1713 the sidepane gate is still wider, and must stay', () => {
  it('an API seat can still set a working folder in the pill sidepane', async () => {
    // The guard against "fixing" #1713 by narrowing the SHARED flag. The pill
    // opens `AgentConfigSidepane`, which has its OWN free-text "Working
    // folder" input for any local-bound seat — including an API agent, whose
    // folder the navbar subtitle reads back. Had the fix narrowed
    // `workspaceFolderEditable` in place instead of splitting the two
    // consumers, this input would have disappeared for API seats and no test
    // would have said so.
    stubFetch(API_SEAT)
    await open('/chat?blueprint=api_codey')
    const pill = await screen.findByTestId('selected-agent-header')
    await act(async () => {
      pill.click()
    })
    // The sidepane's free-text input is a working control for this seat…
    const field = await screen.findByTestId('agent-config-folder')
    expect(field).toBeEnabled()
    // …while the pill's own "Select folder" button, whose destination is the
    // editor, is correctly absent. Both facts at once is the split: one seat,
    // two destinations, two different answers, both correct.
    expect(folderControl()).toBeNull()
  })
})
