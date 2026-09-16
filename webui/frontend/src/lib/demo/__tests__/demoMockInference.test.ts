import { afterEach, describe, expect, it, vi } from 'vitest'
import { parseChatWsMessage } from '../../chatWs'
import { installDemoRuntime } from '../demoMockInference'

describe('installDemoRuntime', () => {
  const originalFetch = window.fetch
  const originalWebSocket = window.WebSocket

  afterEach(() => {
    window.fetch = originalFetch
    window.WebSocket = originalWebSocket
    vi.unstubAllGlobals()
    document.documentElement.removeAttribute('data-demo-mode')
    delete (window as unknown as { __DEMO_RUNTIME__?: boolean }).__DEMO_RUNTIME__
    delete (window as unknown as { __DEMO_INFERENCE__?: unknown }).__DEMO_INFERENCE__
  })

  it('stubs fetch and streams a scripted websocket turn', async () => {
    installDemoRuntime()
    expect(document.documentElement.dataset.demoMode).toBe('true')

    const health = await fetch('/health')
    await expect(health.json()).resolves.toMatchObject({ status: 'ok' })

    const frames: string[] = []
    const ws = new WebSocket('ws://demo.local/ws/ai-demo/c1/')
    ws.onmessage = (ev) => frames.push(String(ev.data))
    await new Promise<void>((resolve) => {
      ws.onopen = () => resolve()
    })
    ws.send(JSON.stringify({ message: 'Build a REST API with the SDLC team' }))

    const kinds = frames.map((raw) => parseChatWsMessage(raw).kind)
    expect(kinds).toContain('spa_hello')
    expect(kinds).toContain('user_echo')
    expect(kinds).toContain('assistant_start')
    expect(kinds).toContain('assistant_chunk')
    expect(kinds).toContain('assistant_final')
    const final = frames.map(parseChatWsMessage).find((e) => e.kind === 'assistant_final')
    expect(final && 'text' in final ? final.text : '').toContain('Product Owner')
  })
})
