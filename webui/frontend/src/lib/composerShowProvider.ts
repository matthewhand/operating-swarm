/**
 * #878: user preference to show/hide the provider routing picker in the
 * message input field.
 *
 * Mirrors the storage + event pattern in `theme.ts`: a localStorage value
 * with a dispatched CustomEvent so `ChatPage` can react without a reload.
 */

export const COMPOSER_SHOW_PROVIDER_STORAGE_KEY = 'swarm_composer_show_provider'
export const COMPOSER_SHOW_PROVIDER_SET_EVENT = 'swarm:set-composer-show-provider'

/** Default is on — most operators want the picker visible. */
export function initialComposerShowProvider(): boolean {
  try {
    const stored = localStorage.getItem(COMPOSER_SHOW_PROVIDER_STORAGE_KEY)
    if (stored === 'false') return false
    if (stored === 'true') return true
  } catch {
    /* storage unavailable — fall through to the default */
  }
  return true
}

export function persistComposerShowProvider(visible: boolean): void {
  try {
    localStorage.setItem(COMPOSER_SHOW_PROVIDER_STORAGE_KEY, String(visible))
  } catch {
    /* persistence is best-effort */
  }
}

export function dispatchSetComposerShowProvider(visible: boolean): void {
  persistComposerShowProvider(visible)
  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent<boolean>(COMPOSER_SHOW_PROVIDER_SET_EVENT, { detail: visible }),
    )
  }
}