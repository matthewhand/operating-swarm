/**
 * #642 — how many agents depend on a provider type, derived from catalog
 * data (#551 doctrine: declared data, never hardcoded kind lists).
 *
 * - CLI providers: the cli-agents payload's `rail` rows count a seat on
 *   `kind === 'cli'` with `cli === <name>`.
 * - Remote instances: the remotes payload carries per-remote `agents` rows;
 *   persisted per-agent remote bindings (localStorage) may add more. An
 *   agent that is both listed and bound counts once.
 *
 * A count of zero means the type is unused and its toggle/remove control
 * behaves exactly as before (#642 keeps unused controls untouched).
 */

import type { CliAgentsInfo } from './api'
import type { RemoteEntry } from './remotesCatalog'
import { AGENT_REMOTE_BINDINGS_KEY } from './agentRemote'

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

export const providerDependents: {
  cli: (info: CliAgentsInfo | null | undefined, cliName: string) => number
  remote: (catalog: RemoteEntry[] | null | undefined, remoteId: string) => number
} = {
  cli(info, cliName) {
    const wanted = cliName.trim().toLowerCase()
    if (!wanted) return 0
    const rail = Array.isArray(info?.rail) ? info.rail : []
    return rail.filter(
      (row) =>
        row &&
        row.kind === 'cli' &&
        String(row.cli || '')
          .trim()
          .toLowerCase() === wanted,
    ).length
  },

  remote(catalog, remoteId) {
    const wanted = remoteId.trim().toLowerCase()
    if (!wanted) return 0
    const entries = Array.isArray(catalog) ? catalog : []
    const listed = new Set<string>()
    for (const entry of entries) {
      if (!entry || String(entry.id || '').trim().toLowerCase() !== wanted) continue
      for (const agent of Array.isArray(entry.agents) ? entry.agents : []) {
        const id = String(agent?.id || '').trim()
        if (id) listed.add(id.toLowerCase())
      }
    }
    // Persisted per-agent bindings live outside the catalog payload; they
    // count too, but an agent that is both listed and bound counts once.
    const bound = new Set<string>()
    try {
      const raw = localStorage.getItem(AGENT_REMOTE_BINDINGS_KEY)
      const rec = raw ? asRecord(JSON.parse(raw) as unknown) : null
      if (rec) {
        for (const [agentId, value] of Object.entries(rec)) {
          const binding = asRecord(value)
          if (!binding) continue
          const id = String(binding.id || '').trim()
          if (!id || id.toLowerCase() !== wanted) continue
          const agent = String(agentId || '').trim()
          if (agent) bound.add(agent.toLowerCase())
        }
      }
    } catch {
      /* storage unavailable / malformed — catalog rows still count */
    }
    for (const agent of bound) listed.delete(agent)
    return listed.size + bound.size
  },
}

/** Tooltip copy. Empty string when unused (control stays enabled, no tip). */
export function providerUsageLabel(count: number): string {
  if (!Number.isFinite(count) || count <= 0) return ''
  const base = 'Agents using this type of provider are still configured'
  return count === 1 ? base : `${base} (${count} agents)`
}
