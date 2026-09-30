/**
 * #1347 — scrolled transcript must never leak outside the message input's
 * bounding box. The sticky composer dock is now full-bleed to the transcript
 * edges with an opaque theme background (it previously left a ~0.25rem strip
 * on each side where scrolled rows bled past the composer).
 *
 * jsdom does not apply external stylesheets, so this test pins BOTH ends:
 *  1. the dock element carries the shroud hook (so the CSS actually applies);
 *  2. the scoped stylesheet full-bleeds + opaques that hook.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ChatBottomDock } from '../ChatBottomDock'

function baseProps(overrides: Record<string, unknown> = {}): Record<string, unknown> {
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

describe('#1347 — composer dock occludes the transcript', () => {
  it('mounts the shroud hook on the sticky dock', () => {
    render(
      // The shroud only beats the transcript padding when it is a child of
      // the transcript scroll container, exactly as the shell renders it.
      <div className="os-chat-transcript">
        <ChatBottomDock
          {...(baseProps() as React.ComponentProps<typeof ChatBottomDock>)}
        />
      </div>,
    )
    const dock = screen.getByTestId('chat-bottom-dock')
    expect(dock).toHaveClass('os-chat-bottom-dock')
    expect(dock).toHaveClass('os-chat-composer-shroud')
    // Opaque base-100 fill so scrolled rows cannot show through.
    expect(dock).toHaveClass('bg-base-100')
    // The old leaky negative margins are gone.
    expect(dock.className).not.toMatch(/-mx-2|sm:-mx-3/)
  })

  it('the scoped stylesheet full-bleeds and opaques the shroud (theme token only)', () => {
    const css = readFileSync(
      resolve(__dirname, '..', 'chatTranscriptOverflow.css'),
      'utf8',
    )
    const start = css.indexOf('.os-chat-transcript .os-chat-bottom-dock.os-chat-composer-shroud')
    expect(start).toBeGreaterThanOrEqual(0)
    const base = css.slice(start)
    // Mobile padding is 0.75rem; >=640px it is 1rem (index.css).
    expect(base).toMatch(/margin-left:\s*-0\.75rem/)
    expect(base).toMatch(/margin-right:\s*-0\.75rem/)
    expect(base).toMatch(/background-color:\s*var\(--color-base-100\)/)
    const media = css.slice(css.indexOf('@media (min-width: 640px)'))
    expect(media).toMatch(/margin-left:\s*-1rem/)
    expect(media).toMatch(/margin-right:\s*-1rem/)
    // Theme tokens only — no hardcoded hex in the declarations (comments may
    // name issue numbers like #1347, so strip them first).
    const declarations = css.replace(/\/\*[\s\S]*?\*\//g, '')
    expect(declarations).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
  })
})
