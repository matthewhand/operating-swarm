/**
 * #1726 — a chat is its own rail row.
 *
 * "New session" on an agent and picking that agent from **+ Add bot** were
 * already ONE code path (`useRailSessionCommands.startNewAgentSession`, wired
 * to both the rail menu and `AddBotMenu.onStartChat`), and both produced the
 * same *invisible* result: a Django session, a URL, and no new row. The
 * operator asked for a second entry in the sidepane, and nothing in the rail
 * could show one, because the rail has exactly one row per seat by
 * construction (`catalogRows` comes from the catalog).
 *
 * So a chat row is a DERIVED row: an id that names both the seat it belongs to
 * and the session it is, plus the little record the sidepane needs to label
 * it. It flows through the same `applyRailOrder` / `partitionRowsBySection` /
 * `railMoveToDestinations` machinery every other row uses — that is the whole
 * point of deriving it rather than bolting on a second list. Django remains
 * canonical; this is the same best-effort local cache `swarm_rail_order` and
 * `swarm_rail_sections` already are.
 *
 * Id shape: `chat:<agentId>:<sessionId>`. Colons are already the rail's own
 * namespace separator (`team:`, `remote:`, `herdr:`), so a chat id is
 * recognisable by prefix and never collides with a slug id.
 */

export const RAIL_CHAT_ROW_PREFIX = 'chat:'
export const RAIL_CHAT_ROWS_STORAGE_KEY = 'swarm_rail_chat_rows'
export const RAIL_CHAT_ROWS_EVENT = 'swarm:rail-chat-rows'

export interface RailChatRow {
  /** `chat:<agentId>:<sessionId>` — the rail id, unique and stable. */
  id: string
  /** The seat row this chat belongs to. */
  agentId: string
  /** The Django/scale-out session id; also the conversation id. */
  sessionId: string
  title: string
  createdAt: number
}

export interface ParsedRailChatRowId {
  agentId: string
  sessionId: string
}

/**
 * `agentId` may itself contain a colon (`team:`/`remote:`/`herdr:` are seat
 * ids, and a future nested id could be one too), so the id is split from the
 * RIGHT: the last segment is the session id and everything between the prefix
 * and it is the agent id.
 */
export function railChatRowId(agentId: string, sessionId: string): string {
  const agent = (agentId || '').trim()
  const session = (sessionId || '').trim()
  if (!agent || !session) return ''
  return `${RAIL_CHAT_ROW_PREFIX}${agent}:${session}`
}

export function isRailChatRowId(id: string | null | undefined): boolean {
  return Boolean(id) && String(id).startsWith(RAIL_CHAT_ROW_PREFIX)
}

export function parseRailChatRowId(id: string | null | undefined): ParsedRailChatRowId | null {
  if (!isRailChatRowId(id)) return null
  const rest = String(id).slice(RAIL_CHAT_ROW_PREFIX.length)
  const cut = rest.lastIndexOf(':')
  if (cut <= 0 || cut === rest.length - 1) return null
  return { agentId: rest.slice(0, cut), sessionId: rest.slice(cut + 1) }
}

/** `/chat?blueprint=<seat>&session=<session>` — the row's own destination. */
export function railChatRowHref(row: Pick<RailChatRow, 'agentId' | 'sessionId'>): string {
  const params = new URLSearchParams()
  params.set('blueprint', row.agentId)
  params.set('session', row.sessionId)
  return `/chat?${params.toString()}`
}

function isChatRow(value: unknown): value is RailChatRow {
  if (!value || typeof value !== 'object') return false
  const row = value as Partial<RailChatRow>
  if (typeof row.id !== 'string' || !row.id) return false
  const parsed = parseRailChatRowId(row.id)
  if (!parsed) return false
  // The id is the source of truth for identity; a record whose id and whose
  // agentId/sessionId disagree is corrupt, not a chat row.
  if (row.agentId !== undefined && row.agentId !== parsed.agentId) return false
  if (row.sessionId !== undefined && row.sessionId !== parsed.sessionId) return false
  return true
}

function normalize(row: RailChatRow): RailChatRow {
  const parsed = parseRailChatRowId(row.id)
  return {
    id: row.id,
    agentId: parsed?.agentId ?? row.agentId,
    sessionId: parsed?.sessionId ?? row.sessionId,
    title: (row.title || '').trim() || 'New chat',
    createdAt: Number.isFinite(row.createdAt) ? row.createdAt : Date.now(),
  }
}

export function parseRailChatRows(raw: string | null): RailChatRow[] {
  if (!raw) return []
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    const seen = new Set<string>()
    const out: RailChatRow[] = []
    for (const item of parsed) {
      if (!isChatRow(item)) continue
      if (seen.has(item.id)) continue
      seen.add(item.id)
      out.push(normalize(item))
    }
    return out
  } catch {
    return []
  }
}

export function loadRailChatRows(): RailChatRow[] {
  try {
    return parseRailChatRows(localStorage.getItem(RAIL_CHAT_ROWS_STORAGE_KEY))
  } catch {
    /* private mode */
    return []
  }
}

export function saveRailChatRows(rows: readonly RailChatRow[]): RailChatRow[] {
  const seen = new Set<string>()
  const next: RailChatRow[] = []
  for (const row of rows) {
    if (!isChatRow(row) || seen.has(row.id)) continue
    seen.add(row.id)
    next.push(normalize(row))
  }
  try {
    if (next.length === 0) localStorage.removeItem(RAIL_CHAT_ROWS_STORAGE_KEY)
    else localStorage.setItem(RAIL_CHAT_ROWS_STORAGE_KEY, JSON.stringify(next))
  } catch {
    /* persistence is best-effort */
  }
  if (typeof window !== 'undefined') {
    try {
      window.dispatchEvent(new CustomEvent(RAIL_CHAT_ROWS_EVENT))
    } catch {
      /* jsdom / SSR */
    }
  }
  return next
}

/** Idempotent: creating a second chat with the same session is the same row. */
export function addRailChatRow(row: RailChatRow): RailChatRow[] {
  const id = row.id || railChatRowId(row.agentId, row.sessionId)
  if (!id) return loadRailChatRows()
  return saveRailChatRows([
    { ...row, id },
    ...loadRailChatRows().filter((existing) => existing.id !== id),
  ])
}

export function removeRailChatRow(id: string): RailChatRow[] {
  if (!isRailChatRowId(id)) return loadRailChatRows()
  return saveRailChatRows(loadRailChatRows().filter((row) => row.id !== id))
}
