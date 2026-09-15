import { openSettingsSheet, type SettingsSection } from '../components/SettingsSheet'

/** In-app Settings pane ids that chat markdown may deep-link. */
const SETTINGS_SECTIONS = new Set<string>([
  'general',
  'definition',
  'blueprint',
  'remotes',
  'retention',
  'hostname',
  'llm-profiles',
  'mcp',
  'cli-agents',
  'roles',
  'sandboxes',
  'rail',
  'image-gen',
  'speech',
  'system',
  'plugins',
])

export const MANAGE_CLI_HREF = '/chat?settings=cli-agents'

function asSettingsSection(value: string | null | undefined): SettingsSection | null {
  const section = String(value || '').trim().toLowerCase()
  if (!section || !SETTINGS_SECTIONS.has(section)) return null
  return section as SettingsSection
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
    const base =
      typeof window !== 'undefined' && window.location?.href
        ? window.location.href
        : 'https://swarm.local/chat'
    const url = new URL(raw, base)
    const baseUrl = new URL(base)
    if (url.origin !== baseUrl.origin) return null
    const section = asSettingsSection(url.searchParams.get('settings'))
    if (!section) return null
    const path = url.pathname.replace(/\/+$/, '') || '/'
    if (path !== '/chat' && path !== '') return null
    return section
  } catch {
    return null
  }
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
  const section = parseSettingsHref(anchor.getAttribute('href'))
  if (!section) return false
  event.preventDefault()
  event.stopPropagation()
  openSettingsSheet({ section })
  return true
}
