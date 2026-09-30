/**
 * #1445: chat header chrome is limited to chat routes. Settings is a non-chat
 * surface even though it overlays a mounted ChatPage.
 */
import { describe, expect, it, afterEach } from 'vitest'
import { headerSeatKey } from '../seatRouting'
import {
  isChatHeaderRoute,
  resetChatHeaderSurfaceForTests,
  setChatHeaderSuppressed,
  shouldShowChatHeader,
} from '../chatHeaderSurface'

describe('#1445 chat header surface', () => {
  afterEach(() => {
    resetChatHeaderSurfaceForTests()
  })

  it('treats only /, /chat, and /chat/* as chat header routes', () => {
    expect(isChatHeaderRoute('/')).toBe(true)
    expect(isChatHeaderRoute('/chat')).toBe(true)
    expect(isChatHeaderRoute('/chat/thread')).toBe(true)
    expect(isChatHeaderRoute('/agents')).toBe(false)
    expect(isChatHeaderRoute('/settings')).toBe(false)
    expect(isChatHeaderRoute('/teams/demo')).toBe(false)
    expect(isChatHeaderRoute('/chatroom')).toBe(false)
  })

  it('clears the header on Settings and other non-chat routes', () => {
    const seat = 'remote:anythingllm'
    expect(shouldShowChatHeader('/agents', false, seat)).toBe(false)
    expect(shouldShowChatHeader('/settings', false, seat)).toBe(false)
    expect(shouldShowChatHeader('/chat', false, seat)).toBe(true)
    expect(shouldShowChatHeader('/', false, seat)).toBe(true)
    setChatHeaderSuppressed(true)
    expect(shouldShowChatHeader('/chat', true, seat)).toBe(false)
    expect(shouldShowChatHeader('/', true, seat)).toBe(false)
    setChatHeaderSuppressed(false)
    expect(shouldShowChatHeader('/chat', false, seat)).toBe(true)
  })

  it('requires a valid seat id — empty and api: are not seats', () => {
    expect(headerSeatKey({})).toBe('api:')
    expect(shouldShowChatHeader('/chat', false, headerSeatKey({}))).toBe(false)
    expect(shouldShowChatHeader('/', false, '')).toBe(false)
    expect(shouldShowChatHeader('/chat', false, 'api:')).toBe(false)
    expect(shouldShowChatHeader('/chat', false, 'remote:')).toBe(false)
    expect(shouldShowChatHeader('/chat', false, 'api:support')).toBe(true)
    expect(shouldShowChatHeader('/chat', false, 'cli:grok')).toBe(true)
    expect(shouldShowChatHeader('/chat', false, 'team:demo-team')).toBe(true)
    expect(shouldShowChatHeader('/agents', false, 'api:support')).toBe(false)
  })
})
