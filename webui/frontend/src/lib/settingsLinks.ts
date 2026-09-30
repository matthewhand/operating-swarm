import {
  isSettingsSection,
  openSettingsSheet,
  settingsDetailFromQuery,
  type SettingsSection,
} from '../components/settings/kernel'

export const MANAGE_CLI_HREF = '/chat?settings=cli-agents'
/** Open the sheet (default pane). Used by generic Settings shortcuts. */
export const SPA_SETTINGS_HREF = '/chat?settings=true'
/** Set inference — Providers / LLM profiles, not the Django dump. */
export const SPA_SETTINGS_INFERENCE_HREF = '/chat?settings=llm-profiles'

function asSettingsSection(value: string | null | undefined): SettingsSection | null {
  const section = String(value || '').trim().toLowerCase()
  if (!section || !isSettingsSection(section)) return null
  return section
}

/**
 * Parse a chat markdown href that should open Settings in-app (REQ-868).
 * Accepts `/chat?settings=cli-agents` and `settings:cli-agents`.
 */
export function parseSettingsHref(href: string | null | undefined): SettingsSection | null {
  if (!href) return null
  const raw = href.trim()
  if (!raw) return null

  const proto = /^settings:([a-z0-9-]+)$/i.exec(raw)
  if (proto) return asSettingsSection(proto[1])

  try {
    const parsed = parseChatSettingsUrl(raw)
    if (!parsed) return null
    return asSettingsSection(parsed)
  } catch {
    return null
  }
}

function parseChatSettingsUrl(raw: string): string | null {
  const base =
    typeof window !== 'undefined' && window.location?.href
      ? window.location.href
      : 'https://swarm.local/chat'
  const url = new URL(raw, base)
  const baseUrl = new URL(base)
  if (url.origin !== baseUrl.origin) return null
  const path = url.pathname.replace(/\/+$/, '') || '/'
  if (path !== '/chat' && path !== '') return null
  return url.searchParams.get('settings')
}

/** Intercept in-chat settings links so they open the sheet without a reload. */
export function handleSettingsLinkClick(event: MouseEvent): boolean {
  if (event.defaultPrevented) return false
  if (event.button !== 0) return false
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return false
  const target = event.target
  if (!(target instanceof Element)) return false
  const anchor = target.closest('a')
  if (!anchor) return false
  const href = anchor.getAttribute('href')
  const section = parseSettingsHref(href)
  if (section) {
    event.preventDefault()
    event.stopPropagation()
    openSettingsSheet({ section })
    return true
  }
  // #1442: /chat?settings=true (and 1) open the sheet without a pane pick.
  if (href && isBareSettingsOpenHref(href)) {
    event.preventDefault()
    event.stopPropagation()
    openSettingsSheet(settingsDetailFromQuery('true') ?? {})
    return true
  }
  return false
}

function isBareSettingsOpenHref(href: string): boolean {
  const proto = /^settings:(true|1)$/i.exec(href.trim())
  if (proto) return true
  try {
    const raw = parseChatSettingsUrl(href.trim())
    return raw === 'true' || raw === '1'
  } catch {
    return false
  }
}
