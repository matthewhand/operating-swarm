/**
 * #1146/#1147/#1148/#1149 — rail + composer UX batch.
 *
 * #1146: ultra-compact (avatar-only) pinned rows hug the avatar (2.25rem).
 * #1147: the divider hit-zone is wide (18px), mirrored for a right-docked
 *        rail, and overlaps the pill on the chat side in both orientations.
 * #1148: while listening, the mic control renders as a stop button (square
 *        glyph, recording styling, same footprint).
 * #1149: a submitted user message appears optimistically (pending) and the
 *        server's user_echo upgrades that row instead of duplicating it.
 */
import { describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fireEvent, render, screen } from '@testing-library/react'
import { ChatBottomDock } from '../../features/chat/ChatBottomDock'

const css = readFileSync(join(__dirname, '..', '..', 'index.css'), 'utf8')

describe('#1146 — ultra-compact pinned rows hug the avatar', () => {
  it('avatar-only rows spend 2.25rem of vertical height, not 2.75rem', () => {
    const block = css.match(
      /\.os-agent-sidebar--avatar-only \.os-agent-row \{[^}]*\}/,
    )?.[0] ?? ''
    expect(block).toContain('min-height: 2.25rem')
    expect(block).toContain('height: 2.25rem')
  })
})

describe('#1147 — divider hit-zone width + right-dock mirror', () => {
  it('hit-zone reaches 8px over the chat pane and 10px into the pane (18px total)', () => {
    const block = css.match(/(?<=^|\n)\.os-rail-resizer \{[^}]*\}/)?.[0] ?? ''
    expect(block).toContain('width: 18px')
    expect(block).toContain('right: -8px')
  })

  it('right-docked rail mirrors the hit-zone and the pill to the chat side', () => {
    const hit = css.match(/\.os-rail-resizer--right \{[^}]*\}/)?.[0] ?? ''
    expect(hit).toContain('left: -8px')
    const pill = css.match(
      /\.os-rail-resizer--right \.os-rail-divider-pill \{[^}]*\}/,
    )?.[0] ?? ''
    expect(pill).toContain('right: 100%')
  })
})

function dockProps(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    ArrowUp: () => null,
    ChatMessageInput: () => <textarea data-testid="enhanced-input" readOnly />,
    ComposerAttachChips: () => null,
    ComposerPluginsBadge: () => null,
    ComposerSlashPopup: () => null,
    ContextUsageBadge: () => null,
    Layers: () => null,
    Mic: () => null,
    Paperclip: () => null,
    Plug: () => null,
    Plus: () => null,
    QueuedSendPane: () => null,
    Reply: () => null,
    Square: () => null,
    SuggestionChips: () => null,
    addToast: vi.fn(),
    authRejected: false,
    status: 'open',
    composerBusy: false,
    composerMenu: {
      addFiles: { enabled: false, reason: '' },
      compact: { enabled: false, reason: '' },
      plugins: { enabled: false, reason: '' },
    },
    composerPlaceholder: 'Message …',
    composerRef: { current: null },
    composerWrapRef: { current: null },
    chipsDisabled: false,
    chooseSuggestion: vi.fn(),
    contextUsage: { tokens: 1 },
    conversationId: 'c1',
    demoChips: [],
    filteredSlashItems: [],
    handleCompact: vi.fn(),
    handleComposerKeyDown: vi.fn(),
    handleComposerPaste: vi.fn(),
    handleInputChange: vi.fn(),
    handleMic: vi.fn(),
    handleSelectSlashItem: vi.fn(),
    handleSend: vi.fn(),
    hasSendableDraft: false,
    input: '',
    interruptRunningTurn: vi.fn(),
    isApiAgent: false,
    isSlashOpen: false,
    messages: [],
    pendingAttachments: [],
    pluginsPanelOpen: false,
    plusOpen: false,
    plusRef: { current: null },
    queued: { rows: [] },
    queuedPaneMaxHeightPx: vi.fn(() => 320),
    setQueuedHoldIds: vi.fn(),
    renderRoutingPicker: () => null,
    recentSlashIds: [],
    removeAttachment: vi.fn(),
    replyTarget: null,
    sendNowHint: false,
    setInput: vi.fn(),
    setPluginsPanelOpen: vi.fn(),
    setPlusOpen: vi.fn(),
    setReplyTarget: vi.fn(),
    setSlashSelectedIndex: vi.fn(),
    setTokenDiagOpen: vi.fn(),
    showContextUsage: false,
    showDemoChips: false,
    showSuggestionChips: false,
    slashQuery: '',
    slashSelectedIndex: 0,
    sttListening: false,
    suggestionChips: [],
    ...overrides,
  }
}

describe('#1148 — mic becomes a stop button while recording', () => {
  it('idle: renders the mic glyph with no recording styling', () => {
    render(<ChatBottomDock {...(dockProps() as unknown as React.ComponentProps<typeof ChatBottomDock>)} />)
    const mic = screen.getByTestId('composer-mic')
    expect(mic.dataset.recording).toBe('false')
    expect(mic.querySelector('.os-composer__stop-glyph')).toBeNull()
  })

  it('recording: square stop glyph + recording class, and clicking stops', () => {
    const handleMic = vi.fn()
    render(<ChatBottomDock {...(dockProps({ sttListening: true, handleMic }) as unknown as React.ComponentProps<typeof ChatBottomDock>)} />)
    const mic = screen.getByTestId('composer-mic')
    expect(mic.dataset.recording).toBe('true')
    expect(mic.className).toContain('os-composer__icon--recording')
    expect(mic.querySelector('.os-composer__stop-glyph')).not.toBeNull()
    expect(mic.getAttribute('aria-label')).toBe('Stop voice input')
    fireEvent.click(mic)
    expect(handleMic).toHaveBeenCalledTimes(1)
  })
})
