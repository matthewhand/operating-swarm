/**
 * #1073 — tablet sticky dock preference.
 *
 * On tablet viewports (640–1023px) the rail can be *docked*: it renders
 * in-flow beside the chat with no backdrop and no auto-dismiss on pick,
 * exactly like desktop — instead of the temporary slide-out drawer.
 * Mobile (< 640px) never docks (no room); desktop (≥ 1024px) is always
 * docked, so this preference only has an effect on the tablet tier.
 *
 * Persisted in localStorage and broadcast via a storage event-style custom
 * event so every mounted listener (App, sidebar) reacts to a toggle from
 * anywhere, mirroring the `railSide` (#816) pattern.
 */

export const TABLET_STICKY_DOCK_STORAGE_KEY = 'os.tabletStickyDock'
export const TABLET_STICKY_DOCK_EVENT = 'os-tablet-sticky-dock-changed'

export function loadTabletStickyDock(): boolean {
  try {
    return window.localStorage.getItem(TABLET_STICKY_DOCK_STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export function saveTabletStickyDock(docked: boolean): void {
  try {
    window.localStorage.setItem(TABLET_STICKY_DOCK_STORAGE_KEY, docked ? '1' : '0')
  } catch {
    // private mode: the toggle still works for this session via the event
  }
  window.dispatchEvent(new CustomEvent(TABLET_STICKY_DOCK_EVENT, { detail: docked }))
}

export function subscribeTabletStickyDock(listener: (docked: boolean) => void): () => void {
  const handler = (event: Event) => {
    const detail = (event as CustomEvent<boolean>).detail
    listener(typeof detail === 'boolean' ? detail : loadTabletStickyDock())
  }
  const storage = (event: StorageEvent) => {
    if (event.key === TABLET_STICKY_DOCK_STORAGE_KEY) {
      listener(event.newValue === '1')
    }
  }
  window.addEventListener(TABLET_STICKY_DOCK_EVENT, handler)
  window.addEventListener('storage', storage)
  return () => {
    window.removeEventListener(TABLET_STICKY_DOCK_EVENT, handler)
    window.removeEventListener('storage', storage)
  }
}
