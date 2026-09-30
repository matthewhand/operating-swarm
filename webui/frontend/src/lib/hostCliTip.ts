/**
 * #1703 — dismissable chat-pane tip for a host CLI that OpenRig detected on
 * PATH but the user has not wired up yet ("opencode detected").
 *
 * Reuses the existing `/v1/cli-agents/` discovery payload (`discovered` =
 * PATH-seeded catalog CLIs, `configured` = opt-in names) rather than adding a
 * second scanner. Detection is PATH/stat only on the server: no auth probe, no
 * subprocess, no network beyond the payload the chat already fetches.
 *
 * Mirrors the roleAgentTip (REQ-191) / defaultLlmTip (REQ-853) pattern:
 * localStorage is immediate, Django prefs `values` sync when
 * /v1/preferences/ is available. The tip never blocks sending.
 *
 * Dismissal granularity (Success #3): the X button is a session dismiss, while
 * "Don't show this again" persists globally for every host-CLI tip so it sticks
 * across reloads and across newly installed CLIs.
 */

import type { CliAgentsInfo } from './api'
import { configuredCliNames, discoveredCliNames } from './cliAgents'
import { fetchUserPrefs, saveUserPrefs } from './userPrefs'

export const HOST_CLI_TIP_STORAGE_KEY = 'swarm_host_cli_tip_dismissed'
export const HOST_CLI_TIP_PREF_KEY = 'host_cli_tip_dismissed'

/**
 * CLIs detected on PATH that the user has not added yet, in the order the
 * payload lists them (backend sorts). Empty string when there is nothing to
 * offer — no CLI on PATH, or every detected CLI is already configured.
 */
export function hostCliDetectedName(info?: CliAgentsInfo | null): string {
  if (!info) return ''
  const configured = new Set(
    configuredCliNames(info).map((name) => name.toLowerCase()),
  )
  for (const name of discoveredCliNames(info)) {
    if (name && !configured.has(name.toLowerCase())) return name
  }
  return ''
}

export function hostCliTipTitle(cliName: string): string {
  return `${cliName} detected`
}

export function hostCliTipBody(cliName: string): string {
  return `OpenRig found ${cliName} on this host's PATH. Add it as a provider to chat with it — or dismiss this and keep using your API models.`
}

export interface HostCliTipOptions {
  /** `GET /v1/cli-agents/` payload. Undefined (still loading / older server) → no tip. */
  info?: CliAgentsInfo | null
  /** Session dismiss (the X button) or the persisted "never again" flag. */
  dismissed?: boolean
}

export function shouldShowHostCliTip(opts: HostCliTipOptions): boolean {
  if (opts.dismissed) return false
  return hostCliDetectedName(opts.info) !== ''
}

export function isHostCliTipDismissed(): boolean {
  try {
    return localStorage.getItem(HOST_CLI_TIP_STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export function prefsHostCliTipDismissed(
  prefs: { values?: Record<string, unknown> } | null | undefined,
): boolean {
  return prefs?.values?.[HOST_CLI_TIP_PREF_KEY] === true
}

export function persistHostCliTipDismissedLocal(): void {
  try {
    localStorage.setItem(HOST_CLI_TIP_STORAGE_KEY, '1')
  } catch {
    /* persistence is best-effort */
  }
}

export async function persistHostCliTipDismissed(): Promise<void> {
  persistHostCliTipDismissedLocal()
  await saveUserPrefs({ values: { [HOST_CLI_TIP_PREF_KEY]: true } })
}

/**
 * Server bag wins when it has dismissed=true. Local dismiss imports once
 * if the extras key is missing.
 */
export async function hydrateHostCliTipDismissed(): Promise<boolean> {
  const local = isHostCliTipDismissed()
  const server = await fetchUserPrefs()
  if (!server) return local
  if (prefsHostCliTipDismissed(server)) {
    persistHostCliTipDismissedLocal()
    return true
  }
  const extras = server.values || {}
  const missing = extras[HOST_CLI_TIP_PREF_KEY] === undefined
  if (local && (server.empty || missing)) {
    await saveUserPrefs({ values: { [HOST_CLI_TIP_PREF_KEY]: true } })
  }
  return local
}
