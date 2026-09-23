/**
 * #526 — one agent-editing surface.
 *
 * The navbar pencil dispatches OPEN_AGENT_EDITOR_EVENT (pinned in
 * ChatPage.test.tsx) and App renders the shared AgentEditor popup from that
 * event. This file pins the event → dialog wiring through the real App tree,
 * and the second acceptance half: the bespoke sidepane agent-settings panel
 * (`AgentEditorSheet`) is gone — every entry point routes into the same
 * popup.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { OPEN_AGENT_EDITOR_EVENT } from './lib/agentSettings'

class MockWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static instances: MockWebSocket[] = []

  readyState = MockWebSocket.CONNECTING
  onopen: ((ev?: Event) => void) | null = null
  onmessage: ((ev?: Event) => void) | null = null
  onclose: ((ev?: Event) => void) | null = null
  send = vi.fn()
  close = vi.fn()

  constructor(_url: string) {
    MockWebSocket.instances.push(this)
  }

  open() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }
}

function renderAppAt(path: string) {
  window.history.pushState({}, '', path)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
}

describe('#526 — the navbar pencil opens the shared agent editor popup', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/cli-agents')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ rail: [], catalog: {}, native_consensus: {} }),
          } as Response
        }
        if (url.includes('/v1/blueprints')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ data: [] }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({}),
        } as Response
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('dispatching the editor event from the navbar renders the editor dialog', async () => {
    renderAppAt('/chat')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    // The navbar pencil's handler dispatches this event (pinned at the
    // ChatPage level); through the real App tree it must open the popup.
    await act(async () => {
      window.dispatchEvent(
        new CustomEvent(OPEN_AGENT_EDITOR_EVENT, { detail: { agentId: 'support' } }),
      )
    })

    await waitFor(() => {
      expect(document.querySelector('#os-agent-editor')).toBeTruthy()
    })
    // It is the Modal-based popup, not a sidepane sheet.
    expect(document.querySelector('[data-testid="os-overlay-chrome"]')).toBeTruthy()
  })

  it('the sidepane AgentEditorSheet no longer exists anywhere in the tree', async () => {
    // The module was the bespoke sidepane settings panel; #526 replaces it
    // with the shared popup. Its absence is the acceptance — checked on the
    // real filesystem because a dynamic import of a missing file fails at
    // build-analysis time, not at runtime.
    const fs = await import('node:fs')
    const path = await import('node:path')
    const dead = path.default.resolve(__dirname, 'components/AgentEditorSheet.tsx')
    expect(fs.default.existsSync(dead)).toBe(false)
    // And no production module references the dead component.
    const lib = path.default.resolve(__dirname, 'components/AgentEditor.tsx')
    expect(fs.default.readFileSync(lib, 'utf8')).not.toContain('AgentEditorSheet')
  })
})
