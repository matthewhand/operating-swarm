import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { OPEN_SETTINGS_EVENT } from '../../components/SettingsSheet'
import { handleSettingsLinkClick, parseSettingsHref } from '../settingsLinks'

describe('parseSettingsHref (REQ-868)', () => {
  it('parses /chat?settings=cli-agents', () => {
    expect(parseSettingsHref('/chat?settings=cli-agents')).toBe('cli-agents')
    expect(parseSettingsHref('/chat?settings=cli-agents&foo=1')).toBe('cli-agents')
  })

  it('parses settings:cli-agents protocol', () => {
    expect(parseSettingsHref('settings:cli-agents')).toBe('cli-agents')
    expect(parseSettingsHref('settings:llm-profiles')).toBe('llm-profiles')
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
