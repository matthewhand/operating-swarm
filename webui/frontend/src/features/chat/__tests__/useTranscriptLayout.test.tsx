import { describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useTranscriptLayout } from '../useTranscriptLayout'

function createDefaultOpts(overrides: Record<string, unknown> = {}) {
  const scrollBox = document.createElement('div')
  Object.defineProperty(scrollBox, 'clientHeight', { value: 600, configurable: true })
  Object.defineProperty(scrollBox, 'scrollHeight', { value: 2000, configurable: true })
  scrollBox.scrollTop = 0

  return {
    messages: [],
    replyTarget: null,
    input: '',
    awaitingAssistant: false,
    selectedAgentName: 'Codey',
    workspaceSubtitle: '',
    status: 'open' as const,
    connectAttempt: 0,
    authRejected: false,
    signInHref: '/sign-in',
    seatUnread: false,
    activeChatAgentId: 'codey',
    conversationId: 'conv-1',
    newBeforeKey: null,
    bottomDockRef: { current: null },
    scrollBoxRef: { current: scrollBox },
    setComposerInsetPx: vi.fn(),
    setTranscriptHeightPx: vi.fn(),
    listEndRef: { current: null },
    composerRef: { current: null },
    pinnedToBottomRef: { current: false },
    composerInsetPx: 0,
    setUnreadIds: vi.fn(),
    addToast: vi.fn(),
    dismissByKind: vi.fn(),
    reconnect: vi.fn(),
    ...overrides,
  }
}

describe('useTranscriptLayout mobile scroll-to-hide header', () => {
  it('hides header on scroll down and restores it on scroll up or near top', () => {
    const opts = createDefaultOpts()
    const { result } = renderHook(() => useTranscriptLayout(opts as any))

    expect(result.current.mobileHeaderHidden).toBe(false)

    // Simulate scrolling down by 50px
    const fakeTarget = {
      scrollTop: 50,
      clientHeight: 600,
      scrollHeight: 2000,
    } as unknown as HTMLElement

    act(() => {
      result.current.handleTranscriptScroll({ currentTarget: fakeTarget } as any)
    })
    expect(result.current.mobileHeaderHidden).toBe(true)

    // Simulate scrolling down further
    const fakeTarget2 = {
      scrollTop: 100,
      clientHeight: 600,
      scrollHeight: 2000,
    } as unknown as HTMLElement

    act(() => {
      result.current.handleTranscriptScroll({ currentTarget: fakeTarget2 } as any)
    })
    expect(result.current.mobileHeaderHidden).toBe(true)

    // Simulate scrolling up by 30px (from 100 to 70)
    const fakeTarget3 = {
      scrollTop: 70,
      clientHeight: 600,
      scrollHeight: 2000,
    } as unknown as HTMLElement

    act(() => {
      result.current.handleTranscriptScroll({ currentTarget: fakeTarget3 } as any)
    })
    expect(result.current.mobileHeaderHidden).toBe(false)

    // Simulate scrolling down again
    const fakeTarget4 = {
      scrollTop: 120,
      clientHeight: 600,
      scrollHeight: 2000,
    } as unknown as HTMLElement

    act(() => {
      result.current.handleTranscriptScroll({ currentTarget: fakeTarget4 } as any)
    })
    expect(result.current.mobileHeaderHidden).toBe(true)

    // Simulate scrolling all the way back to top (scrollTop <= 24)
    const fakeTargetTop = {
      scrollTop: 10,
      clientHeight: 600,
      scrollHeight: 2000,
    } as unknown as HTMLElement

    act(() => {
      result.current.handleTranscriptScroll({ currentTarget: fakeTargetTop } as any)
    })
    expect(result.current.mobileHeaderHidden).toBe(false)
  })
})
