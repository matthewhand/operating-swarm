/**
 * Runtime mock WS + REST for `VITE_DEMO_MODE` (REQ-882 / #279).
 * Extends the e2e helper in `e2e/helpers/mockInference.ts` with scripted flows.
 */

import { escapeHtml } from '../htmlSafe'
import { demoFramesForPrompt, demoSuggestionChips } from './scenarios'
import { stubDemoFetch } from './restStubs'

export type DemoInferenceState = {
  lastPrompt: string | null
  delivered: number
}

function userEchoFrame(text: string): string {
  return `<div id="message-list" hx-swap-oob="beforeend"><div class="user-message">${escapeHtml(text)}</div></div>`
}

function assistantStartFrame(id: string): string {
  return `<div id="message-list" hx-swap-oob="beforeend"><div id="${id}" class="assistant-message"></div></div>`
}

function assistantChunkFrame(id: string, text: string): string {
  return `<div hx-swap-oob="beforeend:#${id}">${escapeHtml(text)}</div>`
}

function assistantFinalFrame(id: string, text: string): string {
  return `<div id="${id}" class="assistant-message" hx-swap-oob="true">${escapeHtml(text)}</div>`
}

function statusFrame(text: string): string {
  return `<div id="message-list" hx-swap-oob="beforeend"><div class="chat-status-line os-chat-status">${escapeHtml(text)}</div></div>`
}

function installFetchStub(): void {
  const original = window.fetch.bind(window)
  window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    const url =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.href
          : input.url
    const stub = stubDemoFetch(url, init)
    if (stub) return Promise.resolve(stub)
    return original(input, init)
  }) as typeof fetch
}

function installWebSocketMock(): void {
  const state: DemoInferenceState = { lastPrompt: null, delivered: 0 }
  ;(window as unknown as { __DEMO_INFERENCE__: DemoInferenceState }).__DEMO_INFERENCE__ = state

  class DemoInferenceWebSocket {
    static CONNECTING = 0
    static OPEN = 1
    static CLOSING = 2
    static CLOSED = 3

    readonly url: string
    readyState = DemoInferenceWebSocket.CONNECTING
    onopen: ((ev: Event) => void) | null = null
    onmessage: ((ev: MessageEvent) => void) | null = null
    onclose: ((ev: CloseEvent) => void) | null = null
    onerror: ((ev: Event) => void) | null = null
    private seq = 0

    constructor(url: string) {
      this.url = url
      queueMicrotask(() => {
        if (this.readyState !== DemoInferenceWebSocket.CONNECTING) return
        this.readyState = DemoInferenceWebSocket.OPEN
        this.onopen?.(new Event('open'))
        this.emit(
          JSON.stringify({
            type: 'spa_hello',
            spa_version: import.meta.env.VITE_SPA_VERSION || 'demo',
          }),
        )
      })
    }

    send(data: string) {
      let prompt = ''
      try {
        const parsed = JSON.parse(data) as { message?: unknown; type?: unknown }
        if (parsed.type === 'cancel_turn') {
          this.emit(JSON.stringify({ type: 'turn_cancelled' }))
          return
        }
        prompt = typeof parsed.message === 'string' ? parsed.message : ''
      } catch {
        return
      }
      if (!prompt.trim()) return
      state.lastPrompt = prompt
      this.emit(userEchoFrame(prompt))

      this.seq += 1
      const id = `message-response-demo${this.seq}`
      this.emit(assistantStartFrame(id))

      const frames = demoFramesForPrompt(prompt)
      const assembled: string[] = []
      for (const frame of frames) {
        if (frame.kind === 'status') this.emit(statusFrame(frame.text))
        else if (frame.kind === 'json') this.emit(JSON.stringify(frame.payload))
        else {
          assembled.push(frame.text)
          this.emit(assistantChunkFrame(id, frame.text))
        }
      }
      const body = assembled.join('')
      this.emit(assistantFinalFrame(id, body))
      this.emit(JSON.stringify({ type: 'suggestions', suggestions: demoSuggestionChips() }))
      state.delivered += 1
    }

    close(code = 1000) {
      if (this.readyState === DemoInferenceWebSocket.CLOSED) return
      this.readyState = DemoInferenceWebSocket.CLOSED
      this.onclose?.(new CloseEvent('close', { code }))
    }

    private emit(data: string) {
      this.onmessage?.(new MessageEvent('message', { data }))
    }
  }

  window.WebSocket = DemoInferenceWebSocket as unknown as typeof WebSocket
}

/** Must run before React mounts. */
export function installDemoRuntime(): void {
  if (typeof window === 'undefined') return
  if ((window as unknown as { __DEMO_RUNTIME__?: boolean }).__DEMO_RUNTIME__) return
  ;(window as unknown as { __DEMO_RUNTIME__: boolean }).__DEMO_RUNTIME__ = true
  document.documentElement.dataset.demoMode = 'true'
  installFetchStub()
  installWebSocketMock()
}
