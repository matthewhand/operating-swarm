/**
 * #856 slice M — the transcript shell is a module.
 *
 * The page frame (tips pills, sr-only status line, the #445/#857
 * os-chat-transcript container with its IRC-gutter rail, message list and
 * bottom dock slots) moves verbatim from ChatPage into
 * features/chat/ChatTranscriptShell.tsx as <ChatTranscriptShell>. The page
 * keeps state; the shell is pure structure.
 *
 * Pinned contract:
 * 1. renders the transcript container with data-agent-kind derived from the
 *    seat (remote > cli > agentKind) and the bubble-theme attributes;
 * 2. renders the IRC gutter rail only when the theme uses it;
 * 3. renders the message list and bottom dock through their slots;
 * 4. the sr-only connection status line renders the label;
 * 5. ChatPage consumes the module (no inline os-chat-transcript JSX).
 */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { ChatTranscriptShell } from '../ChatTranscriptShell'

const base = (over: Record<string, unknown> = {}) => ({
  statusLabel: 'Connected',
  scrollBoxRef: { current: null },
  composerInsetPx: 0,
  composerInsetCustomProperty: () => null,
  bubbleTheme: 'chat',
  getBubbleTheme: () => ({
    messageLayout: 'bubbles',
    timestampPlacement: 'meta',
    actionRowPlacement: 'meta',
  }),
  themeUsesIrcGutter: () => false,
  ircGutterPx: 200,
  ircGutterDragging: false,
  onIrcRailPointerDown: vi.fn(),
  onIrcRailPointerMove: vi.fn(),
  onIrcRailPointerUp: vi.fn(),
  onIrcRailDoubleClick: vi.fn(),
  remoteFromUrl: null,
  isRemoteAgent: false,
  agentKind: 'api',
  isCliAgent: false,
  messagesEditable: true,
  handleTranscriptScroll: vi.fn(),
  ChatMessageList: () => <div data-testid="msg-list" />,
  ChatBottomDock: () => <div data-testid="dock" />,
  ConsumerPills: () => null,
  showRoleTip: false,
  RoleAgentTip: () => null,
  dismissRoleTip: vi.fn(),
  showDefaultLlmTip: false,
  DefaultLlmTip: () => null,
  dismissDefaultLlmTip: vi.fn(),
  activeChatAgentId: 'a1',
  ...over,
})

describe('#856 slice M — ChatTranscriptShell', () => {
  it('renders the transcript container with derived data-agent-kind (api seat)', () => {
    render(<ChatTranscriptShell {...(base() as any)} />)
    const shell = screen.getByRole('log')
    expect(shell.getAttribute('data-agent-kind')).toBe('api')
    expect(shell.getAttribute('data-bubble-theme')).toBe('chat')
    expect(screen.getByTestId('msg-list')).toBeTruthy()
    expect(screen.getByTestId('dock')).toBeTruthy()
  })

  it('derives remote kind from the remote URL before agentKind', () => {
    render(<ChatTranscriptShell {...(base({ remoteFromUrl: 'trueforge' }) as any)} />)
    expect(screen.getByRole('log').getAttribute('data-agent-kind')).toBe('remote')
  })

  it('derives cli kind for CLI seats', () => {
    render(<ChatTranscriptShell {...(base({ isCliAgent: true }) as any)} />)
    expect(screen.getByRole('log').getAttribute('data-agent-kind')).toBe('cli')
  })

  it('renders the IRC gutter rail only when the theme uses it, and it is draggable', () => {
    const { unmount } = render(<ChatTranscriptShell {...(base() as any)} />)
    expect(screen.queryByTestId('irc-gutter-rail')).toBeNull()
    unmount()
    render(<ChatTranscriptShell {...(base({ themeUsesIrcGutter: () => true }) as any)} />)
    const rail = screen.getByTestId('irc-gutter-rail')
    expect(rail.getAttribute('data-dragging')).toBe('false')
    fireEvent.pointerDown(rail)
    // handler was attached (no crash) — the drag wiring is pinned by useIrcGutter tests
  })

  it('renders the sr-only connection status line', () => {
    render(<ChatTranscriptShell {...(base({ statusLabel: 'Offline' }) as any)} />)
    expect(screen.getByRole('status').textContent).toBe('Offline')
  })

  it('ChatPage consumes the module (no inline transcript shell)', () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- source introspection
    const fs = require('node:fs')
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- source introspection
    const path = require('node:path')
    const src = fs.readFileSync(
      path.join(__dirname, '..', '..', '..', 'pages', 'ChatPage.tsx'),
      'utf8',
    )
    // The module is consumed via a spread — #1116 collapsed the named
    // chatShellProps object into allChatScope, so pin the shape, not the
    // historical object name.
    expect(src).toMatch(/<ChatTranscriptShell \{\.\.\.\w+\} \/>/)
    expect(src).not.toContain('os-chat-transcript')
  })
})
