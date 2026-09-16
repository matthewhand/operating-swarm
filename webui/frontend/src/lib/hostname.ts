/**
 * Editable rail hostname. Default is the browser host; an override persists.
 */

export const HOSTNAME_STORAGE_KEY = 'swarm_hostname'

/** Loopback IPs are not a product hostname — show `localhost` in chrome (#400). */
export function displayHostname(host: string): string {
  const h = host.trim().toLowerCase()
  if (h === '127.0.0.1' || h === '0.0.0.0' || h === '::1' || h === '[::1]') {
    return 'localhost'
  }
  return host.trim() || 'localhost'
}

export function defaultHostname(): string {
  try {
    return displayHostname(window.location.hostname || 'localhost')
  } catch {
    return 'localhost'
  }
}

export function loadHostname(): string {
  try {
    const stored = localStorage.getItem(HOSTNAME_STORAGE_KEY)
    if (stored && stored.trim().length > 0) return displayHostname(stored)
  } catch {
    /* storage unavailable */
  }
  return defaultHostname()
}

export function saveHostname(value: string): string {
  const trimmed = value.trim()
  const next = trimmed.length > 0 ? trimmed : defaultHostname()
  try {
    if (next === defaultHostname()) {
      localStorage.removeItem(HOSTNAME_STORAGE_KEY)
    } else {
      localStorage.setItem(HOSTNAME_STORAGE_KEY, next)
    }
  } catch {
    /* persistence is best-effort */
  }
  return next
}

export const HOSTNAME_CHANGED_EVENT = 'swarm:hostname-changed'

export function dispatchHostnameChanged(hostname: string): void {
  try {
    window.dispatchEvent(
      new CustomEvent<{ hostname: string }>(HOSTNAME_CHANGED_EVENT, {
        detail: { hostname },
      }),
    )
  } catch {
    /* ignore in environments without window */
  }
}
