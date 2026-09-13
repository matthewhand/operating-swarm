/**
 * Overlay bus for Grok-Bot chrome (REQ-48).
 *
 * Manage/settings surfaces open as DaisyUI modal / modal-end sheets over the
 * mounted Chat view. They must not become React routes that unmount ChatPage.
 */

export const OPEN_SETTINGS_EVENT = 'swarm:open-settings'
export const OPEN_TEAMS_EVENT = 'swarm:open-teams'
export const OPEN_BLUEPRINTS_EVENT = 'swarm:open-blueprints'
export const OPEN_HIDDEN_EVENT = 'swarm:open-hidden'
export const OPEN_PLUGINS_EVENT = 'swarm:open-plugins'
export const OPEN_ROLE_PANE_EVENT = 'swarm:open-role-pane'
export const OPEN_COMPUTER_CONTROL_EVENT = 'swarm:open-computer-control'
export const OPEN_LLM_PROFILES_EVENT = 'swarm:open-llm-profiles'
export const OVERLAY_CLOSED_EVENT = 'swarm:overlay-closed'

export type ChromeOverlay =
  | 'settings'
  | 'teams'
  | 'blueprints'
  | 'hidden'
  | 'plugins'
  | 'role'
  | 'computer-control'
  | 'llm-profiles'

const EVENT_BY_OVERLAY: Record<ChromeOverlay, string> = {
  settings: OPEN_SETTINGS_EVENT,
  teams: OPEN_TEAMS_EVENT,
  blueprints: OPEN_BLUEPRINTS_EVENT,
  hidden: OPEN_HIDDEN_EVENT,
  plugins: OPEN_PLUGINS_EVENT,
  role: OPEN_ROLE_PANE_EVENT,
  'computer-control': OPEN_COMPUTER_CONTROL_EVENT,
  'llm-profiles': OPEN_LLM_PROFILES_EVENT,
}

export interface RolePaneDetail {
  roleId?: string
}

/** Opaque floating pane — page must not bleed through (Settings / add-profile). */
export const OVERLAY_CHROME_CLASSES =
  'bg-base-100 border border-base-300 shadow-xl'

export function openChromeOverlay(overlay: ChromeOverlay, detail?: RolePaneDetail): void {
  window.dispatchEvent(new CustomEvent(EVENT_BY_OVERLAY[overlay], { detail }))
}

/** Chat composer listens so closing a sheet restores the same input. */
export function notifyOverlayClosed(): void {
  window.dispatchEvent(new CustomEvent(OVERLAY_CLOSED_EVENT))
}
