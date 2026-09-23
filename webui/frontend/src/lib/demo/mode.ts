/** REQ-882 / #279: client-side public demo flag (`VITE_DEMO_MODE`). */

export function isDemoMode(): boolean {
  const value = import.meta.env.VITE_DEMO_MODE
  return value === 'true' || value === '1'
}
