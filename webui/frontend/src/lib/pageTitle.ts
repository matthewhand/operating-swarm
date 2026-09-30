/**
 * #1225 — the browser tab title mirrors the server label.
 *
 * `Operating Swarm: <hostname>` — multi-host operators differentiate tabs at
 * a glance. The title is derived from the same source the rail footer shows
 * (`loadHostname()`), so editing the server name anywhere (rail footer,
 * Settings, prefs sync) updates the tab live via HOSTNAME_CHANGED_EVENT,
 * USER_PREFS_CHANGED_EVENT, and cross-tab `storage` writes.
 */

import { HOSTNAME_CHANGED_EVENT, loadHostname } from './hostname'
import { USER_PREFS_CHANGED_EVENT } from './userPrefs'

export const APP_TITLE_PREFIX = 'Operating Swarm'

/** Compose the tab title; empty/missing names fall back to `localhost`. */
export function pageTitleFor(hostname: string | null | undefined): string {
  const name = (hostname ?? '').trim() || 'localhost'
  return `${APP_TITLE_PREFIX}: ${name}`
}

/** Re-derive the title from the current hostname preference. */
function refreshTitle(): void {
  try {
    document.title = pageTitleFor(loadHostname())
  } catch {
    /* no DOM — nothing to do */
  }
}

/**
 * Install the title reactions. Returns an uninstaller (test isolation /
 * HMR): every listener is removed and nothing fires afterwards.
 */
export function installPageTitle(): () => void {
  refreshTitle()

  const onHostnameChanged = () => refreshTitle()
  const onPrefsChanged = () => refreshTitle()
  const onStorage = (event: StorageEvent) => {
    // Only hostname writes need a re-read; anything else leaves the title.
    if (event.key === null || event.key === 'swarm_hostname') refreshTitle()
  }

  try {
    window.addEventListener(HOSTNAME_CHANGED_EVENT, onHostnameChanged)
    window.addEventListener(USER_PREFS_CHANGED_EVENT, onPrefsChanged)
    window.addEventListener('storage', onStorage)
  } catch {
    /* no window — install is a no-op beyond the initial refresh */
  }

  return () => {
    try {
      window.removeEventListener(HOSTNAME_CHANGED_EVENT, onHostnameChanged)
      window.removeEventListener(USER_PREFS_CHANGED_EVENT, onPrefsChanged)
      window.removeEventListener('storage', onStorage)
    } catch {
      /* ignore */
    }
  }
}
