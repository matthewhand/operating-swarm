/**
 * Client-side custom roles persistence and event dispatching.
 *
 * Synchronizes custom roles locally in localStorage (with offline support)
 * and dispatches swarm:custom-roles-updated events so the settings pane,
 * agent editor, and sidepane stay reactive.
 */

import type { RoleDescriptor } from './api'

export const CUSTOM_ROLES_KEY = 'swarm_custom_roles'
export const CUSTOM_ROLES_UPDATED_EVENT = 'swarm:custom-roles-updated'

export function emitCustomRolesUpdated(): void {
  try {
    window.dispatchEvent(new CustomEvent(CUSTOM_ROLES_UPDATED_EVENT))
  } catch {
    /* ignore in environments without DOM */
  }
}

export function loadCustomRoles(): RoleDescriptor[] {
  try {
    const raw = localStorage.getItem(CUSTOM_ROLES_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (r): r is RoleDescriptor =>
        Boolean(r && typeof r === 'object' && typeof r.name === 'string' && r.name.trim()),
    )
  } catch {
    return []
  }
}

export function saveCustomRole(role: RoleDescriptor): void {
  try {
    const current = loadCustomRoles()
    const name = role.name.trim().toLowerCase().replace(/\s+/g, '_').replace(/-/g, '_')
    const item: RoleDescriptor = {
      ...role,
      name,
      custom: true,
    }
    const idx = current.findIndex((r) => r.name === name)
    if (idx >= 0) {
      current[idx] = item
    } else {
      current.push(item)
    }
    localStorage.setItem(CUSTOM_ROLES_KEY, JSON.stringify(current))
    emitCustomRolesUpdated()
  } catch {
    /* persistence is best effort */
  }
}

export function deleteCustomRole(roleName: string): void {
  try {
    const current = loadCustomRoles()
    const name = roleName.trim().toLowerCase().replace(/\s+/g, '_').replace(/-/g, '_')
    const next = current.filter((r) => r.name !== name)
    localStorage.setItem(CUSTOM_ROLES_KEY, JSON.stringify(next))
    emitCustomRolesUpdated()
  } catch {
    /* persistence is best effort */
  }
}

export function findCustomRole(roleName: string): RoleDescriptor | undefined {
  if (!roleName) return undefined
  const norm = roleName.trim().toLowerCase().replace(/\s+/g, '_').replace(/-/g, '_')
  return loadCustomRoles().find(
    (r) => r.name === norm || r.aliases?.some((a) => a.toLowerCase() === norm),
  )
}
