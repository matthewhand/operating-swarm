import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  applyFontFamily,
  CUSTOM_FONT_FAMILY_STORAGE_KEY,
  DEFAULT_FONT_FAMILY,
  FONT_FAMILIES,
  FONT_FAMILY_CHANGED_EVENT,
  FONT_FAMILY_LABELS,
  FONT_FAMILY_STACKS,
  FONT_FAMILY_STORAGE_KEY,
  loadCustomFontFamily,
  loadFontFamily,
  normalizeCustomFontFamily,
  OS_FONT_FAMILY_ATTR,
  OS_FONT_FAMILY_VAR,
  parseFontFamily,
  saveCustomFontFamily,
  saveFontFamily,
} from '../fontFamily'

function rootVar(): string {
  return document.documentElement.style.getPropertyValue(OS_FONT_FAMILY_VAR)
}

describe('#1227 fontFamily', () => {
  afterEach(() => {
    localStorage.removeItem(FONT_FAMILY_STORAGE_KEY)
    localStorage.removeItem(CUSTOM_FONT_FAMILY_STORAGE_KEY)
    document.documentElement.style.removeProperty(OS_FONT_FAMILY_VAR)
    document.documentElement.removeAttribute(OS_FONT_FAMILY_ATTR)
    vi.unstubAllGlobals()
  })

  it('exposes the ticket presets with labels and stacks', () => {
    // #1244 added the self-hosted Hack code font; #1227 shipped the rest.
    expect(FONT_FAMILIES).toEqual(['omarchy', 'hack', 'monospace', 'sans', 'serif', 'custom'])
    for (const id of FONT_FAMILIES) {
      expect(FONT_FAMILY_LABELS[id]).toBeTruthy()
    }
    expect(FONT_FAMILY_STACKS.omarchy).toContain("'JetBrainsMono Nerd Font'")
    expect(FONT_FAMILY_STACKS.hack).toContain('Hack')
    expect(FONT_FAMILY_STACKS.monospace).toContain('ui-monospace')
    expect(FONT_FAMILY_STACKS.sans).toContain("'Noto Sans'")
    expect(FONT_FAMILY_STACKS.serif).toContain('ui-serif')
  })

  it('defaults to the Omarchy-compatible stack', () => {
    expect(DEFAULT_FONT_FAMILY).toBe('omarchy')
    expect(loadFontFamily()).toBe('omarchy')
    expect(parseFontFamily(null)).toBe('omarchy')
    expect(parseFontFamily('')).toBe('omarchy')
    expect(parseFontFamily(42)).toBe('omarchy')
  })

  it('parses known presets, folds legacy system, and maps raw stacks to custom', () => {
    expect(parseFontFamily('monospace')).toBe('monospace')
    expect(parseFontFamily('sans')).toBe('sans')
    expect(parseFontFamily('serif')).toBe('serif')
    expect(parseFontFamily('system')).toBe('omarchy')
    expect(parseFontFamily("'My Font', sans-serif")).toBe('custom')
  })

  it('persists the chosen preset and applies it to the root', () => {
    expect(saveFontFamily('monospace')).toBe('monospace')
    expect(localStorage.getItem(FONT_FAMILY_STORAGE_KEY)).toBe('monospace')
    expect(loadFontFamily()).toBe('monospace')
    expect(rootVar()).toContain('ui-monospace')
    expect(document.documentElement.getAttribute(OS_FONT_FAMILY_ATTR)).toBe('monospace')
  })

  it('stores and applies an operator custom stack', () => {
    expect(saveFontFamily("'Fira Code', monospace")).toBe('custom')
    expect(localStorage.getItem(FONT_FAMILY_STORAGE_KEY)).toBe('custom')
    expect(loadCustomFontFamily()).toBe("'Fira Code', monospace")
    expect(loadFontFamily()).toBe('custom')
    expect(rootVar()).toContain('Fira Code')
    expect(document.documentElement.getAttribute(OS_FONT_FAMILY_ATTR)).toBe('custom')
  })

  it('sanitizes dangerous characters and caps the custom stack length', () => {
    const cleaned = normalizeCustomFontFamily('Arial; } body { color: red')
    expect(cleaned).toContain('Arial')
    expect(cleaned).toContain('color: red')
    expect(cleaned).not.toContain(';')
    expect(cleaned).not.toContain('{')
    expect(cleaned).not.toContain('}')
    expect(normalizeCustomFontFamily('<script>x</script>')).not.toContain('<')
    expect(normalizeCustomFontFamily('a'.repeat(400))).toHaveLength(160)
  })

  it('dispatches the changed event for presets and custom alike', () => {
    const seen: unknown[] = []
    const onChange = (event: Event) => seen.push((event as CustomEvent).detail)
    window.addEventListener(FONT_FAMILY_CHANGED_EVENT, onChange)
    saveFontFamily('serif')
    saveCustomFontFamily("'X', serif")
    window.removeEventListener(FONT_FAMILY_CHANGED_EVENT, onChange)
    expect(seen).toEqual(['serif', 'custom'])
  })

  it('clearing the custom stack falls back to the default stack', () => {
    saveCustomFontFamily("'Fira Code', monospace")
    expect(rootVar()).toContain('Fira Code')
    saveCustomFontFamily('')
    expect(localStorage.getItem(CUSTOM_FONT_FAMILY_STORAGE_KEY)).toBeNull()
    expect(rootVar()).toBe('')
    expect(document.documentElement.hasAttribute(OS_FONT_FAMILY_ATTR)).toBe(false)
  })

  it('re-applying the persisted value is a no-op idempotent pass', () => {
    applyFontFamily('sans')
    expect(document.documentElement.getAttribute(OS_FONT_FAMILY_ATTR)).toBe('sans')
    applyFontFamily()
    expect(document.documentElement.getAttribute(OS_FONT_FAMILY_ATTR)).toBe('omarchy')
    expect(rootVar()).toContain("'JetBrainsMono Nerd Font'")
  })
})
