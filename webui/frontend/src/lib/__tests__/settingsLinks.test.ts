import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { OPEN_SETTINGS_EVENT, SETTINGS_SECTIONS } from '../../components/SettingsSheet'
import {
  handleSettingsLinkClick,
  parseSettingsHref,
  SPA_SETTINGS_HREF,
  SPA_SETTINGS_INFERENCE_HREF,
} from '../settingsLinks'

describe('parseSettingsHref (REQ-868)', () => {
  it('parses /chat?settings=cli-agents', () => {
    expect(parseSettingsHref('/chat?settings=cli-agents')).toBe('cli-agents')
    expect(parseSettingsHref('/chat?settings=cli-agents&foo=1')).toBe('cli-agents')
  })

  it('parses settings:cli-agents protocol', () => {
    expect(parseSettingsHref('settings:cli-agents')).toBe('cli-agents')
    expect(parseSettingsHref('settings:llm-profiles')).toBe('llm-profiles')
  })

  it('accepts every canonical kernel section (no divergent allowlist)', () => {
    for (const section of SETTINGS_SECTIONS) {
      expect(parseSettingsHref(`settings:${section}`)).toBe(section)
      expect(parseSettingsHref(`/chat?settings=${section}`)).toBe(section)
    }
  })

  it('parses the sections a stale allowlist used to drop', () => {
    expect(parseSettingsHref('settings:experimental')).toBe('experimental')
    expect(parseSettingsHref('settings:backend-audit')).toBe('backend-audit')
    expect(parseSettingsHref('settings:providers')).toBe('providers')
  })

  it('treats /chat?settings=true as a bare open, not a section (#1442)', () => {
    expect(parseSettingsHref(SPA_SETTINGS_HREF)).toBeNull()
    expect(parseSettingsHref(SPA_SETTINGS_INFERENCE_HREF)).toBe('llm-profiles')
  })

  it('rejects unknown sections and non-settings hrefs', () => {
    expect(parseSettingsHref('/chat?settings=not-a-pane')).toBeNull()
    expect(parseSettingsHref('https://example.com/chat?settings=cli-agents')).toBeNull()
    expect(parseSettingsHref('/docs?settings=cli-agents')).toBeNull()
    expect(parseSettingsHref('https://example.com/path')).toBeNull()
    expect(parseSettingsHref('')).toBeNull()
    expect(parseSettingsHref(null)).toBeNull()
  })
})

describe('handleSettingsLinkClick (REQ-868)', () => {
  const opened: unknown[] = []
  const listener = (event: Event) => opened.push((event as CustomEvent).detail)

  beforeEach(() => {
    opened.length = 0
    window.addEventListener(OPEN_SETTINGS_EVENT, listener)
  })

  afterEach(() => {
    window.removeEventListener(OPEN_SETTINGS_EVENT, listener)
  })

  it('opens Settings at cli-agents and prevents default navigation', () => {
    const root = document.createElement('div')
    root.innerHTML = '<a href="/chat?settings=cli-agents">Manage CLI</a>'
    const link = root.querySelector('a')!
    const event = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 })
    Object.defineProperty(event, 'target', { value: link })
    const prevented = handleSettingsLinkClick(event)
    expect(prevented).toBe(true)
    expect(event.defaultPrevented).toBe(true)
    expect(opened).toEqual([{ section: 'cli-agents' }])
  })

  it('opens Settings from /chat?settings=true without a pane pick (#1442)', () => {
    const root = document.createElement('div')
    root.innerHTML = `<a href="${SPA_SETTINGS_HREF}">Settings</a>`
    const link = root.querySelector('a')!
    const event = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 })
    Object.defineProperty(event, 'target', { value: link })
    expect(handleSettingsLinkClick(event)).toBe(true)
    expect(event.defaultPrevented).toBe(true)
    expect(opened).toEqual([{}])
  })

  it('opens LLM profiles from the Set inference href (#1442)', () => {
    const root = document.createElement('div')
    root.innerHTML = `<a href="${SPA_SETTINGS_INFERENCE_HREF}">Set inference</a>`
    const link = root.querySelector('a')!
    const event = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 })
    Object.defineProperty(event, 'target', { value: link })
    expect(handleSettingsLinkClick(event)).toBe(true)
    expect(opened).toEqual([{ section: 'llm-profiles' }])
  })

  it('ignores ordinary links', () => {
    const root = document.createElement('div')
    root.innerHTML = '<a href="https://example.com/docs">docs</a>'
    const link = root.querySelector('a')!
    const event = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 })
    Object.defineProperty(event, 'target', { value: link })
    expect(handleSettingsLinkClick(event)).toBe(false)
    expect(event.defaultPrevented).toBe(false)
    expect(opened).toEqual([])
  })
})
