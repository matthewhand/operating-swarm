/**
 * Opt-in CLI agents catalog (REQ-157 / #565) plus CLI-first start set (#149).
 *
 * ``known`` / ``clis`` is the full catalog (documentation). ``discovered`` /
 * ``installed`` is the PATH seed and the rail/picker starting set. ``configured``
 * is empty until + Add. Suggestions are discovered-minus-configured. One-click
 * Add persists like remotes; Remove drops the name from configured (the binary
 * may still reappear as a suggestion). Pi absent on a host stays absent.
 */

import type { CliAgentsInfo } from './api'

/** Last native-select item — navigates to Settings → CLI agents. */
export const ADD_CLI_VALUE = '__add_cli__'

export const KNOWN_CLI_NAMES = [
  'agy',
  'claude',
  'codex',
  'gemini',
  'grok',
  'opencode',
  'pi',
] as const

export function configuredCliNames(info?: CliAgentsInfo | null): string[] {
  const listed = info?.configured
  if (Array.isArray(listed)) {
    return listed.map((name) => String(name).trim()).filter(Boolean)
  }
  return []
}

export function discoveredCliNames(info?: CliAgentsInfo | null): string[] {
  const listed = info?.discovered ?? info?.installed
  if (Array.isArray(listed)) {
    return listed.map((name) => String(name).trim()).filter(Boolean)
  }
  return []
}

export function suggestedCliEntries(
  info?: CliAgentsInfo | null,
): Array<{ name: string; cmd: string[] }> {
  const configured = new Set(configuredCliNames(info))
  const suggestions = info?.suggestions
  if (suggestions && typeof suggestions === 'object') {
    return Object.entries(suggestions)
      .filter(([name]) => name.trim() && !configured.has(name.trim()))
      .map(([name, entry]) => ({
        name,
        cmd: Array.isArray((entry as { cmd?: string[] } | undefined)?.cmd)
          ? ((entry as { cmd: string[] }).cmd)
          : [name],
      }))
      .sort((a, b) => a.name.localeCompare(b.name))
  }
  return discoveredCliNames(info)
    .filter((name) => !configured.has(name))
    .map((name) => {
      const cmd = (info?.catalog?.[name] as { cmd?: string[] } | undefined)?.cmd
      return { name, cmd: Array.isArray(cmd) && cmd.length ? cmd : [name] }
    })
}

export function cliSelectPlaceholder(configuredCount: number, selectedId = ''): string {
  if (configuredCount === 0) return 'No CLI agents'
  // #1093 (5): 'default' beats imperative 'Pick a …'.
  if (!selectedId) return 'default'
  return 'CLI'
}

export type CompactCliStatus = 'configured' | 'detected' | 'not-detected'

export type CompactCliRow = {
  name: string
  status: CompactCliStatus
  cmd: string[]
}

/** `cli:grok` → `grok`. Other provider ids return null. */
export function focusedCliName(focusProviderId?: string | null): string | null {
  const raw = (focusProviderId || '').trim()
  if (!raw.toLowerCase().startsWith('cli:')) return null
  return raw.slice(raw.indexOf(':') + 1).trim() || null
}

function asCmd(raw: unknown, fallback: string): string[] {
  if (Array.isArray(raw) && raw.length) {
    return raw.map((part) => String(part)).filter(Boolean)
  }
  return [fallback]
}

/** Compact Settings list: configured, PATH-detected, then optional unavailable. */
export function compactCliRows(
  info?: CliAgentsInfo | null,
  configData: Record<string, { cmd?: string[] }> = {},
  opts: { showUnavailable?: boolean; focusName?: string | null } = {},
): CompactCliRow[] {
  const configured = new Set<string>([
    ...configuredCliNames(info),
    ...Object.keys(configData)
      .map((name) => name.trim())
      .filter(Boolean),
  ])
  const discovered = new Set(discoveredCliNames(info))
  const knownSource = info?.known ?? info?.clis ?? [...KNOWN_CLI_NAMES]
  const known = knownSource.map((name) => String(name).trim()).filter(Boolean)

  const names = new Set<string>()
  for (const name of configured) names.add(name)
  for (const name of discovered) names.add(name)
  if (opts.showUnavailable) {
    for (const name of known) names.add(name)
  }
  const focus = (opts.focusName || '').trim()
  if (focus) names.add(focus)

  const rank: Record<CompactCliStatus, number> = {
    configured: 0,
    detected: 1,
    'not-detected': 2,
  }

  return [...names]
    .map((name) => {
      const status: CompactCliStatus = configured.has(name)
        ? 'configured'
        : discovered.has(name)
          ? 'detected'
          : 'not-detected'
      const fromConfig = configData[name]?.cmd
      const fromSuggest = (info?.suggestions?.[name] as { cmd?: string[] } | undefined)?.cmd
      const fromCatalog = (info?.catalog?.[name] as { cmd?: string[] } | undefined)?.cmd
      return { name, status, cmd: asCmd(fromConfig ?? fromSuggest ?? fromCatalog, name) }
    })
    .sort((a, b) => rank[a.status] - rank[b.status] || a.name.localeCompare(b.name))
}

/**
 * Split a CLI string into [command, ...args] on unquoted whitespace.
 * Quotes group arguments with spaces without invoking an arbitrary shell.
 */
export function splitCliString(cli: string): string[] {
  const out: string[] = []
  let cur = ''
  let quote: '"' | "'" | null = null
  for (const ch of cli.trim()) {
    if (quote) {
      if (ch === quote) quote = null
      else cur += ch
    } else if (ch === '"' || ch === "'") {
      quote = ch
    } else if (/\s/.test(ch)) {
      if (cur) out.push(cur)
      cur = ''
    } else {
      cur += ch
    }
  }
  if (cur) out.push(cur)
  return out
}

