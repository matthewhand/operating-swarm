/**
 * #1700 (2) — the manage link in a blueprint-not-found chat error is clickable.
 *
 * The backend fix appends `[Manage blueprints](settings:blueprint)` to the
 * error. That is only a fix if four things hold downstream, and three of them
 * are JavaScript:
 *
 * 1. the chat renders the text as an assistant message (`chatWs.ts`);
 * 2. `renderSafeMarkdown` keeps the `settings:` href (the sanitizer allow-lists
 *    it, REQ-868) — if that allowlist ever narrowed, the link would be stripped
 *    and the error would be a dead end again, *silently*, with the backend
 *    text unchanged;
 * 3. `parseSettingsHref` resolves it to the `blueprint` pane.
 *
 * (1) is covered in Python by `tests/views/test_blueprint_missing_manage_link_1700.py`,
 * which pins the oob element shape `chatWs.ts` keys on. This file covers 2 and 3
 * against the real text the backend emits.
 */

import { describe, expect, it } from 'vitest'
import { renderSafeMarkdown } from '../markdown'
import { parseSettingsHref } from '../settingsLinks'

/** Byte-for-byte the text `stubs_mixin.respond_with_blueprint` sends. */
const BACKEND_ERROR =
  "Error: blueprint 'cos' was not found or could not be initialized. " +
  '[Manage blueprints](settings:blueprint)'

describe(String.raw`the error manage link is a real control`, () => {
  it('the sanitizer keeps the settings: href and emits a live anchor', () => {
    const html = renderSafeMarkdown(BACKEND_ERROR)
    expect(html).toContain('href="settings:blueprint"')
    expect(html).toContain('>Manage blueprints</a>')
  })

  it('the SPA resolves that href to the Blueprints pane', () => {
    expect(parseSettingsHref('settings:blueprint')).toBe('blueprint')
  })

  it('the diagnosis survives alongside the link', () => {
    const text = renderSafeMarkdown(BACKEND_ERROR)
    // Strip tags so this reads the operator-visible sentence, not the markup.
    const visible = text.replace(/<[^>]+>/g, '')
    expect(visible).toContain("blueprint 'cos' was not found or could not be initialized")
    expect(visible).toContain('Manage blueprints')
  })

  it('the sanitizer still refuses a javascript: href in the same position', () => {
    // The link is a fix, not a hole: the allow-list is a positive list, and
    // this is the case that would break if someone widened it to every scheme.
    const html = renderSafeMarkdown('[Manage](javascript:alert(1))')
    expect(html).not.toContain('javascript:')
  })
})
