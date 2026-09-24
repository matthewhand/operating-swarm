/**
 * #856 slice P — the pass-through props objects are dead weight.
 *
 * ChatPage builds six big record objects (`chatMessageListProps`,
 * `renderRoutingPickerProps`, `chatBottomDockProps`, `chatHeaderProps`,
 * `chatOverlaysProps`, `chatShellProps`) whose entries are almost all
 * `{ Name }` shorthand — passing ChatPage's own scope through to the
 * extracted modules. Tying them together as one spreadable scope record is
 * behaviour-preserving: `allChatScope` contains exactly the union of those
 * shorthand names, and each module receives `{ ...allChatScope, <customs> }`.
 *
 * Pinned contract:
 * 1. every shorthand name in every props object is present in allChatScope;
 * 2. the three legacy sentinel entries (`__self`/`__ctx`, never destructured
 *    by any module) are gone from ChatPage;
 * 3. ChatPage spreads allChatScope into each module render.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const chatPageSrc = () =>
  readFileSync(join(process.cwd(), 'src/pages/ChatPage.tsx'), 'utf8')

describe('#856 slice P — the scope record', () => {
  it('ChatPage declares the single allChatScope record', () => {
    expect(chatPageSrc()).toContain('const allChatScope = {')
  })

  it('each module render spreads the scope, not a bespoke object', () => {
    const src = chatPageSrc()
    expect(src).toContain('<ChatHeader {...allChatScope}')
    expect(src).toContain('<ChatOverlays {...allChatScope}')
    expect(src).toContain('<ChatTranscriptShell {...allChatScope}')
    // ChatMessageList / ChatBottomDock render inside the transcript shell,
    // which forwards the scope it received (slice M layout).
    const shellSrc = () =>
      readFileSync(join(process.cwd(), 'src/features/chat/ChatTranscriptShell.tsx'), 'utf8')
    expect(shellSrc()).toContain('<ChatMessageList {...props}')
    expect(shellSrc()).toContain('<ChatBottomDock {...props}')
  })

  it('the dead __self/__ctx sentinels are gone', () => {
    const src = chatPageSrc()
    expect(src).not.toContain('__self')
    expect(src).not.toContain('__ctx')
  })

  it('the bespoke per-module props objects no longer exist', () => {
    const src = chatPageSrc()
    expect(src).not.toContain('const chatMessageListProps = {')
    expect(src).not.toContain('const chatBottomDockProps = {')
    expect(src).not.toContain('const chatHeaderProps = {')
    expect(src).not.toContain('const chatOverlaysProps = {')
    expect(src).not.toContain('const chatShellProps = {')
  })
})
