/**
 * #1699 / #1700 — the one reader of the catalog's admission + readiness fields.
 *
 * `GET /v1/blueprints/` is the only "what seats exist" endpoint the SPA reads
 * (the rail, the composer picker and `/v1/models`' model ids are all views onto
 * it), so before #1699 it advertised every shipped recipe as a seat: a
 * greenfield install listed `remote_harness` as an agent it could chat to, and
 * listed seats whose provider could not resolve as chat targets that failed
 * with `blueprint '…' was not found or could not be initialized`.
 *
 * The server now answers both questions per row (`swarm.core.vanilla_seats`).
 * This module is the only place that reads those fields, for two reasons:
 *
 * 1. **Fail-open in one place.** A backend older than the gate sends none of
 *    them. Every field here is optional, and a missing field reads as "listed
 *    and ready" — so an older server can never hide a working seat, and the
 *    next backend that adds a field cannot produce a second, disagreeing rule.
 * 2. **No re-derivation.** Deciding "is this a remote seat?" from the id in the
 *    SPA would be a *second* copy of `agent_kind.classify_agent_kind`, and the
 *    two would drift the first time a recipe is renamed.
 *
 * The rule itself, in words: a row that cannot run a turn is *not* a silent
 * chat target. It is either withheld from the seat list (#1699) or shown with
 * its reason and a repair link (#1700).
 */

import type { Blueprint, SeatKindName, SeatManageLink } from './api'

export interface SeatOfferView {
  id: string
  kind: SeatKindName | 'other'
  source: 'discovery' | 'user' | 'other'
  /** May this row appear as a seat in the rail / agent picker? */
  listed: boolean
  /** Can it run a turn right now? */
  ready: boolean
  /** Operator words for why not. Empty when ready, and never invented here. */
  reason: string
  /** In-product repair routes. Empty when ready. */
  manageLinks: SeatManageLink[]
}

const SEAT_KINDS: ReadonlySet<string> = new Set<SeatKindName>([
  'api',
  'cli',
  'remote',
  'team',
  'blueprint',
])

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

/** A repair link is only useful if it has both halves. Drop the rest. */
export function parseManageLinks(raw: unknown): SeatManageLink[] {
  if (!Array.isArray(raw)) return []
  const out: SeatManageLink[] = []
  for (const item of raw) {
    const rec = asRecord(item)
    if (!rec) continue
    const href = typeof rec.href === 'string' ? rec.href.trim() : ''
    const label = typeof rec.label === 'string' ? rec.label.trim() : ''
    if (href && label) out.push({ href, label })
  }
  return out
}

/**
 * One row's verdict. Absent fields mean an older server, and read as ready —
 * see the module docstring.
 */
export function parseSeatOffer(row: Pick<Blueprint, 'id'>): SeatOfferView {
  // The wire payload is untyped JSON; one narrowing view, used only here.
  const raw = row as Record<string, unknown>
  const rawKind = typeof raw.seat_kind === 'string' ? raw.seat_kind.trim().toLowerCase() : ''
  const rawSource =
    typeof raw.seat_source === 'string' ? raw.seat_source.trim().toLowerCase() : ''
  const listed = raw.seat_listed !== false
  const ready = raw.chat_ready !== false
  return {
    id: String(row.id ?? '').trim(),
    kind: (SEAT_KINDS.has(rawKind) ? rawKind : 'other') as SeatOfferView['kind'],
    source: (rawSource === 'user' || rawSource === 'discovery'
      ? rawSource
      : 'other') as SeatOfferView['source'],
    listed,
    ready,
    // A reason with no route to act on is the dead-end #1700 complained about,
    // so the route list is what makes the reason worth rendering; the text is
    // still passed through either way, because the operator reads it first.
    reason: typeof raw.unavailable_reason === 'string' ? raw.unavailable_reason.trim() : '',
    manageLinks: parseManageLinks(raw.manage_links),
  }
}

/** Every catalog row's verdict, keyed by id. */
export function seatOffersById(
  rows: readonly Pick<Blueprint, 'id'>[] | null | undefined,
): Map<string, SeatOfferView> {
  const out = new Map<string, SeatOfferView>()
  for (const row of rows ?? []) {
    const offer = parseSeatOffer(row)
    if (offer.id) out.set(offer.id, offer)
  }
  return out
}

/**
 * #1699: the rows a first-run install must not offer as agents.
 *
 * A shipped Remote-kind recipe on a host with no configured remote. Operator
 * rows are never withheld — installing a seat is the operator's own act, and
 * hiding it would lose their work.
 */
export function withheldSeatIds(
  rows: readonly Pick<Blueprint, 'id'>[] | null | undefined,
): string[] {
  const out: string[] = []
  for (const row of rows ?? []) {
    const offer = parseSeatOffer(row)
    if (!offer.id) continue
    if (offer.listed) continue
    if (offer.source === 'user') continue
    out.push(offer.id)
  }
  return out
}

/** The rows an agent picker may offer: everything the server did not withhold. */
export function selectableSeats<T extends Blueprint>(rows: readonly T[] | null | undefined): T[] {
  const withheld = new Set(withheldSeatIds(rows))
  return (rows ?? []).filter((row) => !withheld.has(String(row?.id ?? '')))
}

/** True when the row is a visible-but-unavailable seat with a repair route. */
export function needsRepairOffer(offer: SeatOfferView | undefined): boolean {
  return Boolean(offer && offer.listed && !offer.ready)
}

/**
 * The rows an agent picker may offer, with unrunnable ones marked.
 *
 * #1699: a row the server withheld is **dropped** — that is the literal
 * criterion ("does not list Remote-kind seats in the rail or agent picker").
 *
 * #1700: a row that is listed but not ready is **kept and annotated**, never
 * dropped. Dropping it would hide the recipe and leave the operator wondering
 * where the agent they were told about went; keeping it silent is the dead end
 * the issue reported. The reason is appended to the existing `description`
 * slot rather than a new field, so no picker render path has to learn a new
 * prop — and when the reason is empty the row renders exactly as before.
 */
export function pickerSeatRows<
  T extends { id: string; name: string; description?: string },
>(rows: readonly T[] | null | undefined): T[] {
  const offers = seatOffersById(rows)
  const out: T[] = []
  for (const row of rows ?? []) {
    const offer = offers.get(String(row.id))
    if (!offer) {
      out.push(row)
      continue
    }
    if (!offer.listed) continue
    if (offer.ready || !offer.reason) {
      out.push(row)
      continue
    }
    const link = offer.manageLinks[0]?.label
    const suffix = link ? `${offer.reason} → ${link}` : offer.reason
    out.push({ ...row, description: [row.description, suffix].filter(Boolean).join(' — ') })
  }
  return out
}
