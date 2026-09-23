/**
 * #566: per-agent backend audit log — what backend a send actually used, and
 * why it resolved that way.
 *
 * Written from the **send path itself** (the same `currentCli` value the WS
 * frame carries), so the log cannot disagree with reality — a second
 * derivation is exactly how the "remote agent labelled qwen" misreport
 * happened. CLI resolutions carry their source (`param` / `persisted` /
 * `declared` / `inferred` / `none`); an `inferred` fallback is recorded and
 * shown as inferred, never as fact.
 *
 * localStorage + `storage` events, the same pattern as `agentSessions` /
 * `currentAgent`: the Settings sheet is a sibling of ChatPage, not a
 * descendant, and other tabs should stay honest too. Append-only, newest
 * first, capped so a long session cannot grow it without bound.
 */

export interface BackendAuditEntry {
  /** Seat id the rail/URL uses (blueprint id, team:/remote:-prefixed scope). */
  agentId: string
  /** Display name at send time. */
  agentName: string
  kind: 'cli' | 'api' | 'remote' | 'blueprint'
  /** The backend actually sent: CLI name, or profile/remote id for API seats. */
  backend: string
  /** Why the CLI resolved: `param` / `persisted` / `declared` / `inferred` / `none`. */
  source: string
  /** Human-readable provenance sentence for the Settings pane. */
  reason: string
  at: number
}

export const BACKEND_AUDIT_STORAGE_KEY = 'swarm_backend_audit'
export const BACKEND_AUDIT_MAX = 200

/** Tolerant reader — junk is dropped, never thrown. */
export function readBackendAudit(): BackendAuditEntry[] {
  try {
    const raw = window.localStorage.getItem(BACKEND_AUDIT_STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (row): row is BackendAuditEntry =>
        Boolean(row) &&
        typeof row === 'object' &&
        typeof (row as BackendAuditEntry).agentId === 'string' &&
        typeof (row as BackendAuditEntry).backend === 'string' &&
        typeof (row as BackendAuditEntry).at === 'number',
    )
  } catch {
    return []
  }
}

/**
 * Record one send's resolved backend. Pass `cliSource: null` for non-CLI
 * seats — their backend is whatever the API/remote path resolved, not a CLI.
 */
export function recordBackendUse(entry: {
  agentId: string
  agentName: string
  kind: BackendAuditEntry['kind']
  backend: string
  cliSource?: string | null
}): void {
  if (!entry.agentId.trim()) return
  const source = entry.cliSource ?? null
  const reason =
    source === null
      ? entry.kind === 'remote'
        ? 'remote provider own model selection'
        : 'API profile resolution'
      : source === 'param'
        ? 'chosen in the URL for this chat'
        : source === 'persisted'
          ? 'persisted dropdown choice (global)'
          : source === 'declared'
            ? 'the agent declares this CLI'
            : source === 'inferred'
              ? 'inferred fallback — no CLI declared; first available was picked'
              : 'no CLI resolved'
  const row: BackendAuditEntry = {
    agentId: entry.agentId.trim(),
    agentName: entry.agentName.trim() || entry.agentId.trim(),
    kind: entry.kind,
    backend: entry.backend.trim() || '(none)',
    source: source ?? 'n/a',
    reason,
    at: Date.now(),
  }
  try {
    const next = [row, ...readBackendAudit().filter((old) => !sameSend(old, row))].slice(
      0,
      BACKEND_AUDIT_MAX,
    )
    window.localStorage.setItem(BACKEND_AUDIT_STORAGE_KEY, JSON.stringify(next))
    window.dispatchEvent(new Event('swarm:backend-audit'))
  } catch {
    // Storage full or unavailable — the audit is best-effort by design.
  }
}

/** Collapse repeats: same seat+backend+source within 60s is one line, not spam. */
function sameSend(a: BackendAuditEntry, b: BackendAuditEntry): boolean {
  return (
    a.agentId === b.agentId &&
    a.backend === b.backend &&
    a.source === b.source &&
    Math.abs(a.at - b.at) < 60_000
  )
}
