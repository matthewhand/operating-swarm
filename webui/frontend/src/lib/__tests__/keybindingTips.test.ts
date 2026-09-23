import { describe, expect, it } from 'vitest'
import { pinsShortcutLabel, searchShortcutLabel } from '../keybindingTips'

describe('keybinding shortcut labels', () => {
  it('exposes platform-aware Search and pin shortcut labels', () => {
    const search = searchShortcutLabel()
    const pins = pinsShortcutLabel()
    expect(search === '⌘K' || search === 'Ctrl+K').toBe(true)
    // #1088: sequential Alt+↑/↓ replaced the Alt+1–9 slot keys.
    expect(pins === '⌥↑/↓' || pins === 'Alt+↑/↓').toBe(true)
  })
})
