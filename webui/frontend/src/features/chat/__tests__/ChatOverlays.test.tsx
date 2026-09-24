/**
 * #856 slice L — the chat overlay cluster is a module.
 *
 * The message context menu, TokenDiagnosticsModal, SkillPopup,
 * RawResponseModal, start-from-here ConfirmModal, GenerationsPanel, and
 * SessionPicker move verbatim from ChatPage into
 * features/chat/ChatOverlays.tsx as <ChatOverlays>, driven by explicit
 * props. Pinned contract:
 *
 * 1. the context menu renders Reply/Copy items and closes on pick;
 * 2. the modals mount with the same props ChatPage passed (token diag,
 *    skill popup, raw response);
 * 3. ChatPage renders <ChatOverlays {...chatOverlaysProps} /> and carries
 *    none of the overlay JSX inline.
 */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { ChatOverlays } from '../ChatOverlays'

const base = (over: Record<string, unknown> = {}) => ({
  contextMenu: null,
  setContextMenu: vi.fn(),
  setReplyTarget: vi.fn(),
  composerRef: { current: null },
  selectedAgentName: 'Codey',
  isApiAgent: true,
  agentKind: 'api',
  contextStrategy: 'cull',
  handleContextToHere: vi.fn(),
  copyTextToClipboard: vi.fn().mockResolvedValue('ok'),
  toastError: vi.fn(),
  COPY_EMPTY_TITLE: 't', COPY_EMPTY_MESSAGE: 'm',
  COPY_FAILED_TITLE: 't', COPY_FAILED_MESSAGE: 'm',
  Reply: () => null, Copy: () => null, FoldVertical: () => null,
  START_CONTEXT_FROM_HERE_TOOLTIP: 'tip', START_CONTEXT_FROM_HERE_LABEL: 'Start context from here',
  tokenDiagOpen: false,
  setTokenDiagOpen: vi.fn(),
  conversationId: 'c1',
  tokenCount: 0, contextMax: 0, inputTokens: 0, outputTokens: 0,
  summaries: [], toolCallsCount: 0, messages: [],
  userMessageCount: 0, assistantMessageCount: 0,
  contextMeta: {},
  openSkillName: null,
  setOpenSkillName: vi.fn(),
  skillCatalog: [],
  rawResponseModalText: null,
  setRawResponseModalText: vi.fn(),
  startFromHereWarning: null,
  setStartFromHereWarning: vi.fn(),
  applyStartFromHere: vi.fn(),
  generationsOpen: false,
  setGenerationsOpen: vi.fn(),
  headerFaceAgentId: 'a1',
  generationContexts: [],
  seatToolCalls: [],
  remoteThreadPicker: null,
  setRemoteThreadPicker: vi.fn(),
  remoteFromUrl: null,
  setSearchParams: vi.fn(),
  TokenDiagnosticsModal: ({ isOpen }: any) =>
    isOpen ? <div data-testid="token-diag" /> : null,
  SkillPopup: ({ open }: any) => (open ? <div data-testid="skill-popup" /> : null),
  RawResponseModal: ({ isOpen }: any) => (isOpen ? <div data-testid="raw-response" /> : null),
  ConfirmModal: ({ isOpen, children }: any) => (isOpen ? <div>{children}</div> : null),
  GenerationsPanel: ({ open }: any) => (open ? <div data-testid="gens" /> : null),
  SessionPicker: ({ open }: any) => (open ? <div data-testid="session-picker" /> : null),
  ...over,
})

describe('#856 slice L — ChatOverlays', () => {
  it('renders nothing prominent when all overlays are closed', () => {
    render(<ChatOverlays {...(base() as any)} />)
    expect(screen.queryByTestId('token-diag')).toBeNull()
    expect(screen.queryByTestId('message-context-menu')).toBeNull()
  })

  it('the message context menu renders Reply and Copy items', () => {
    render(
      <ChatOverlays
        {...(base({
          contextMenu: {
            x: 10, y: 10, selectedText: 'hi',
            message: { key: 'k1', role: 'assistant', text: 'msg' },
          },
        }) as any)}
      />,
    )
    expect(screen.getByTestId('message-context-menu')).toBeTruthy()
    expect(screen.getByTestId('context-menu-reply').textContent).toContain('Reply to quote')
    expect(screen.getByTestId('context-menu-copy').textContent).toContain('Copy selection')
  })

  it('Reply closes the menu and targets the composer', () => {
    const setContextMenu = vi.fn()
    const setReplyTarget = vi.fn()
    render(
      <ChatOverlays
        {...(base({
          contextMenu: {
            x: 10, y: 10, selectedText: '',
            message: { key: 'k1', role: 'user', text: 'msg' },
          },
          setContextMenu,
          setReplyTarget,
        }) as any)}
      />,
    )
    fireEvent.click(screen.getByTestId('context-menu-reply'))
    expect(setContextMenu).toHaveBeenCalledWith(null)
    expect(setReplyTarget).toHaveBeenCalled()
  })

  it('mounts TokenDiagnostics, Generations, and SessionPicker with ChatPage props', () => {
    render(
      <ChatOverlays
        {...(base({
          tokenDiagOpen: true,
          generationsOpen: true,
          remoteThreadPicker: [{ id: 's1' }],
        }) as any)}
      />,
    )
    expect(screen.getByTestId('token-diag')).toBeTruthy()
    expect(screen.getByTestId('gens')).toBeTruthy()
    expect(screen.getByTestId('session-picker')).toBeTruthy()
  })

  it('ChatPage consumes the module (no inline overlay JSX)', () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- source introspection
    const fs = require('node:fs')
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- source introspection
    const path = require('node:path')
    const src = fs.readFileSync(
      path.join(__dirname, '..', '..', '..', 'pages', 'ChatPage.tsx'),
      'utf8',
    )
    expect(src).toContain('<ChatOverlays {...allChatScope} />')
    expect(src).not.toContain('message-context-menu')
  })
})
