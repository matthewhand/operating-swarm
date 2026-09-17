import { describe, it, expect, beforeEach, vi } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import AgentAvatar from '../../components/AgentAvatar'
import { ToastProvider } from '../../components/DaisyUI/Toast'
import ChatPage from '../ChatPage'

describe('REQ-176: Blob eyes wander while agent is working/streaming', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('swarm:avatar-theme', 'blobs')
    Element.prototype.scrollIntoView = vi.fn()
  })

  it('sets data-eye-state to active when active=true and idle when active=false on AgentAvatar', () => {
    const { container: idleContainer } = render(
      <AgentAvatar agentId="codey" active={false} size="lg" />,
    )
    const idleSvg = idleContainer.querySelector('.os-blob-avatar')
    expect(idleSvg).toHaveAttribute('data-eye-state', 'idle')

    const { container: activeContainer } = render(
      <AgentAvatar agentId="codey" active={true} size="lg" />,
    )
    const activeSvg = activeContainer.querySelector('.os-blob-avatar')
    expect(activeSvg).toHaveAttribute('data-eye-state', 'active')
  })

  it('leaves header blob eyes idle when connected but not streaming', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    // Mock WebSocket to connect cleanly
    class MockWs {
      static OPEN = 1
      readyState = 1
      onopen: ((ev?: Event) => void) | null = null
      onmessage: ((ev?: Event) => void) | null = null
      onclose: ((ev?: Event) => void) | null = null
      send = vi.fn()
      close = vi.fn()
      addEventListener = vi.fn()
      removeEventListener = vi.fn()
    }
    vi.stubGlobal('WebSocket', MockWs as any)

    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat?blueprint=codey']}>
            <ChatPage />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )

    // Header avatar should have idle eye state when no streaming message is present
    const headerAvatar = document.querySelector('.os-chat-header__avatar .os-blob-avatar')
    if (headerAvatar) {
      expect(headerAvatar).toHaveAttribute('data-eye-state', 'idle')
    }

    // Composer working indicator should not be visible when idle
    expect(screen.queryByTestId('composer-working-indicator')).not.toBeInTheDocument()
  })
})

/**
 * #110: REQ-176 shipped motion for the *working* pose only, so an idle blob was
 * a frozen rest pose — and `wanderEyePose()`, the idle wander, was never wired.
 * jsdom has no layout or animation engine, so the idle contract is asserted
 * against the stylesheet, which is where the idle motion lives.
 */
describe('#110: idle blob eyes are animated, not frozen', () => {
  const css = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')

  /**
   * Every brace-matched body for `selector`, in source order.
   *
   * Matched by scanning with a depth counter rather than `[^}]*`: keyframe
   * bodies and at-rule blocks contain nested braces, so a non-greedy body match
   * truncates at the first stop and would silently under-assert (it did — the
   * blink and the active wander checks both "passed" against a one-stop slice).
   */
  function blocksFor(selector: string): string[] {
    const out: string[] = []
    let from = 0
    for (;;) {
      const at = css.indexOf(selector, from)
      if (at === -1) break
      const open = css.indexOf('{', at + selector.length)
      if (open === -1) break
      let depth = 0
      let end = -1
      for (let i = open; i < css.length; i += 1) {
        if (css[i] === '{') depth += 1
        else if (css[i] === '}') {
          depth -= 1
          if (depth === 0) {
            end = i
            break
          }
        }
      }
      if (end === -1) break
      out.push(css.slice(open + 1, end))
      from = end + 1
    }
    return out
  }

  function blockFor(selector: string): string {
    return blocksFor(selector)[0] ?? ''
  }

  it('gives the idle eyes their own animation', () => {
    const idle = blockFor('.os-blob-avatar[data-eye-state="idle"] .os-blob-eyes')
    expect(idle, 'idle eye rule missing — eyes stay frozen when not working').toBeTruthy()
    expect(idle).toMatch(/animation:\s*os-blob-idle/)
    // Per-agent offset must be preserved, or every blob blinks in lockstep.
    expect(idle).toMatch(/var\(--ew/)
    // Slower than the working pose — idle motion must not read as activity.
    expect(idle).toMatch(/calc\(var\(--ed/)
  })

  it('defines an idle keyframe that blinks (a held vertical squash)', () => {
    const frames = blockFor('@keyframes os-blob-idle')
    expect(frames, '@keyframes os-blob-idle missing').toBeTruthy()
    // A blink is a squash toward zero on the Y axis, held across two stops.
    expect(frames).toMatch(/scale\(var\(--es,\s*1\),\s*0\.\d+\)/)
    expect(frames).toMatch(/46%,\s*\n?\s*52%/)
    // Rest pose must be reachable at both ends so the loop does not jump.
    expect(frames).toMatch(/0%,\s*\n?\s*100%/)
    expect(frames).toMatch(/scale\(var\(--es,\s*1\)\)/)
  })

  it('leaves the working pose intact', () => {
    const active = blockFor('.os-blob-avatar[data-eye-state="active"] .os-blob-eyes')
    expect(active).toMatch(/animation:\s*os-blob-wander/)
    const activeFrames = blockFor('@keyframes os-blob-wander')
    // The working wander travels further than the idle drift.
    expect(activeFrames).toMatch(/3\.4px/)
  })

  it('honours prefers-reduced-motion for the idle animation too', () => {
    // Several reduced-motion blocks exist in the sheet; pick the one that owns
    // the blob idle rule rather than whichever comes first in the file.
    const reduced = blocksFor('@media (prefers-reduced-motion: reduce)').find((body) =>
      body.includes('.os-blob-avatar') && body.includes('[data-eye-state="idle"]'),
    )
    expect(reduced, 'idle animation is not covered by prefers-reduced-motion').toBeTruthy()
    expect(reduced).toMatch(/\[data-eye-state="idle"\]\s*\.os-blob-eyes/)
    expect(reduced).toMatch(/animation:\s*none/)
  })
})
