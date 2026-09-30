/**
 * REQ-116: Left rail resizer constants and persistence helpers.
 *
 * #765 adds a third rail state below avatar-only: fully collapsed (0px,
 * divider-only). Snap physics on drag are: < collapse threshold → 0px,
 * else ≤ avatar threshold → avatar rail, else smooth continuous width.
 *
 * #1289 adds pinned-grid column snap points: the drag "sticks" at the rail
 * widths that exactly fit N pinned-grid columns, with the avatar-only tier as
 * its own detent between collapsed and one column.
 * See `RAIL_SNAP_POINTS` for the geometry math.
 *
 * #1683 makes that ladder a function of the PIN COUNT, not a fixed 1/2/3 list:
 *
 *  - A column detent is only worth having if the operator's own pins ask for
 *    it, so the rigid column stops are `1..min(pins, MAX_PINNED_COLUMNS)`
 *    columns — with 2 pins the 3-column stop (302) describes nothing on screen
 *    and is not a detent. See `railSnapPointsForPins`.
 *  - "3 columns" was never a cap, only the last number anyone wrote down:
 *    `railWidthForColumns(4)` = 394px fits inside `MAX_RAIL_WIDTH` (420), and
 *    the grid really does grow a 4th track. `MAX_PINNED_COLUMNS` states the
 *    measured ceiling (4) instead of inheriting a hand-written 3.
 *  - Above the topmost column detent the rail free-tracks to the ceiling
 *    (`railSnapThresholdForPins`). That is safe — and measured, not assumed:
 *    with `justify-content: start` a tile's x depends only on its column index,
 *    and every pin sits in the first row at or above `railWidthForColumns(pins)`,
 *    so widening past the topmost detent adds empty tracks without moving a
 *    single tile. Below it, `cols < pins` for some pin, that tile changes
 *    column on every boundary crossing — that is the #1262 wobble, and
 *    `RAIL_DETENT_ALWAYS` still suppresses it.
 */

export const MIN_RAIL_WIDTH = 68
export const MAX_RAIL_WIDTH = 420
export const DEFAULT_RAIL_WIDTH = 256
/**
 * #1350: the ultra-compact (avatar-only) ceiling. Shaved from 96px to 88px
 * (~8.3%) so the compact rail wastes less horizontal room; the avatar face
 * (2.25rem) and icon hit-areas stay untouched, so nothing clips.
 */
export const AVATAR_ONLY_THRESHOLD = 88
/** #765: below this dragged width the rail snaps fully shut (0px). */
export const COLLAPSE_SNAP_THRESHOLD = 52
/** #765: the fully collapsed divider-only state — border + pill only. */
export const COLLAPSED_RAIL_WIDTH = 0
export const RAIL_WIDTH_STORAGE_KEY = 'swarm_rail_width'

/* ────────────────────────────────────────────────────────────────────────
 * #1289 pinned-grid column snap geometry
 *
 * `.os-fav-grid` (index.css) is `repeat(auto-fill, 5.25rem)` with
 * `gap: 0.5rem` and `margin: 0.35rem 0.75rem 0.5rem`; tiles are a fixed
 * 5.25rem square centred in their track (`justify-items: center`).
 *
 * At a 16px root, one track = 5.25rem = 84px and one grid gap = 0.5rem = 8px.
 * For N columns the grid's *content* box (inside the rail) must supply:
 *
 *     gridContent(N) = N·TRACK + (N-1)·GAP
 *                    = N·84 + (N-1)·8      → 84 / 176 / 268 px
 *
 * The grid's border-box adds the horizontal margins (0.75rem × 2 = 24px) and
 * a conservative chrome reserve (RAIL_CHROME_PX) covering the pane border and
 * the scroll container's `scrollbar-gutter: stable` reserve.
 * Rounding up to whole pixels keeps a full track:
 * 1 col = 118px, 2 cols = 210px, 3 cols = 302px, 4 cols = 394px.
 * All four stay below MAX_RAIL_WIDTH (420px) at the 16px root; a 5th needs
 * 486px and does not. `MAX_PINNED_COLUMNS` counts that rather than assuming it.
 *
 * These are the widths the grid *reflows at*, but NOT where it reflows: the
 * rail also carries a pane border and a `scrollbar-gutter: stable` reserve, so
 * the real column boundaries sit ~10px lower (measured: 2 cols at ~201px, 3 at
 * ~295, 4 at ~387 — `scripts/measure-pinned-grid.mjs --by-pins`). `RAIL_CHROME_PX`
 * is exactly that reserve, which is why each detent lands on the desired column
 * count and not one short.
 * ──────────────────────────────────────────────────────────────────────── */
/** One pinned-grid tile track: 5.25rem at a 16px root. */
export const FAV_TILE_TRACK_PX = 84
/** `.os-fav-grid` column gap: 0.5rem at a 16px root. */
export const FAV_GRID_GAP_PX = 8
/** `.os-fav-grid` horizontal margin (0.75rem left + 0.75rem right). */
export const FAV_GRID_MARGIN_PX = 24
/** Conservative chrome reserve: pane border + the `scrollbar-gutter: stable`
 * reserve owned by the scroll container (#1261). */
export const RAIL_CHROME_PX = 10

/** Rail width that exactly fits N pinned-grid columns (see math above). */
export function railWidthForColumns(columns: number): number {
  const cols = Math.max(1, Math.floor(columns))
  const gridContent = cols * FAV_TILE_TRACK_PX + (cols - 1) * FAV_GRID_GAP_PX
  return Math.ceil(gridContent + FAV_GRID_MARGIN_PX + RAIL_CHROME_PX)
}

/**
 * #1683: how many pinned-grid columns the rail can actually SEAT, counted from
 * the geometry rather than written down.
 *
 * This is the distinction the old fixed ladder papered over: "3 columns" was
 * never a cap, it was just the last entry in a hand-maintained list. The grid
 * reflows at every track boundary regardless (it is `repeat(auto-fill, 5.25rem)`),
 * so nothing stopped a 4th column from appearing — the ladder simply stopped
 * *detenting* at 302. Measured: 4 columns need 394px ≤ `MAX_RAIL_WIDTH`, 5 need
 * 486px > it. Four is the ceiling; five is impossible.
 */
function countColumnsThatFit(): number {
  let columns = 1
  while (railWidthForColumns(columns + 1) <= MAX_RAIL_WIDTH) columns += 1
  return columns
}
export const MAX_PINNED_COLUMNS = countColumnsThatFit()

/** 1 / 2 / 3 / 4 pinned-grid columns → 118 / 210 / 302 / 394 px. */
export const ONE_COL_RAIL_WIDTH = railWidthForColumns(1)
export const TWO_COL_RAIL_WIDTH = railWidthForColumns(2)
export const THREE_COL_RAIL_WIDTH = railWidthForColumns(3)
/** #1683: the 4th column the old ladder never detented at — 394px, still inside
 * `MAX_RAIL_WIDTH` (420). */
export const FOUR_COL_RAIL_WIDTH = railWidthForColumns(4)

/**
 * #1683: the column detents in ascending order, index 0 = one column. Sliced by
 * `railColumnDetents`, which is the only thing that should read it.
 */
const RAIL_COLUMN_DETENTS: readonly number[] = Array.from(
  { length: MAX_PINNED_COLUMNS },
  (_, i) => railWidthForColumns(i + 1),
)

/**
 * #1683: the column detents a pin count EARNS — the widths that exactly fit
 * `1..min(pins, MAX_PINNED_COLUMNS)` columns.
 *
 * This is the operator's rule made arithmetic: "be rigid based on the NUMBER of
 * pinned agents … With 2 pinned agents, be rigid to the 2-column detent, then
 * allow free-form scaling past that." A 3-column stop is only a stop if three
 * pins are asking for three columns.
 *
 * A pin count is a *conservative* count (the stored pin list, a superset of the
 * tiles actually rendered) so it can only leave a detent in place when it need
 * not be, never drop one while a tile is on screen.
 */
export function railColumnDetents(pinnedCount: number): readonly number[] {
  const columns = Math.min(
    Math.max(Math.floor(pinnedCount) || 0, 0),
    MAX_PINNED_COLUMNS,
  )
  return RAIL_COLUMN_DETENTS.slice(0, columns)
}

/** The ultra-compact (avatar-only) detent — one avatar per row. */
export const ULTRACOMPACT_RAIL_WIDTH = AVATAR_ONLY_THRESHOLD
/**
 * #1683: the `.os-fav-grid` declarations this module's column math is derived
 * from, inlined so the two can be checked against each other in a unit test
 * (jsdom never applies the stylesheet, so nothing else can catch a drift).
 * Source: `src/index.css`, `.os-fav-grid`.
 */
export const RAIL_COLUMN_GEOMETRY_CSS = `
  grid-template-columns: repeat(auto-fill, 5.25rem);
  gap: 0.5rem;
  margin: 0.35rem 0.75rem 0.5rem;
  justify-content: start;
  justify-items: center;
`
/** Pointer slop (px) inside which a dragged edge sticks to a snap point. */
export const RAIL_SNAP_THRESHOLD = 14

/**
 * #1262 follow-up — force every drag frame onto a detent.
 *
 * A free-tracking drag walks the pinned grid's column count as a function of
 * the pointer (one more pixel crosses a track boundary), so the tiles reflow
 * under the cursor mid-drag and the rail reads as "wobbling" rather than
 * resizing. Passing this as the snap threshold quantizes the live width to the
 * nearest pinned-grid detent, so the grid only reflows when the operator
 * actually leaves a detent. The default `RAIL_SNAP_THRESHOLD` keeps the
 * historical free-tracking behaviour for callers that want it.
 *
 * #1683: this constant is a workaround for the pinned grid's presence, so it
 * is only ever applied while that grid is on screen — see
 * `railSnapThresholdForPins` and `useRailResize`'s `pinnedCount`. It must not
 * outlive its cause, and it must not be deleted.
 *
 * #1683 refined *where* it applies. The wobble is not "any free-tracking drag
 * near the grid" — it is "a free-tracking drag that crosses a track boundary
 * while some pin is NOT in the first row". Measured against the real rail
 * (`scripts/measure-pinned-grid.mjs`, `--by-pins`):
 *
 *     210→420px, 2 pins : tile x = [13], [105]   ← constant, no wobble
 *     302→420px, 3 pins : tile x = [13], [105], [197]  ← constant
 *     394→420px, 4 pins : tile x = [13], [105], [197], [289]  ← constant
 *     118→209px, 3 pins : tile x = [13], [13, 102.59, 105]  ← MOVES
 *
 * At or above `railWidthForColumns(pins)` every pin is in row 1 at a fixed
 * column, so extra width only appends empty tracks. Below it, `cols < pins` for
 * some pin, and that tile jumps column on each boundary — the #1262 wobble.
 * Hence: quantise up to and including the topmost column detent, free-track
 * above it.
 */
export const RAIL_DETENT_ALWAYS = Number.POSITIVE_INFINITY

/**
 * #1289 / #1651 the ordered detents the rail drag sticks to, low → high:
 * fully collapsed (0px divider-only) → ultra-compact / avatar-only (88) →
 * one column (118) → two (210) → three (302) → four (394) → max (420).
 *
 * This is the FULL ladder — every column count the rail can seat. It is the
 * detent set for a pin pool that has earned all of them (`MAX_PINNED_COLUMNS`),
 * and the superset every narrower pin count draws from. It is NOT the set a
 * given rail uses: use `railSnapPointsForPins(pinnedCount)`.
 *
 * #1651: every stop is a real geometric detent — collapsed, avatar-only, a
 * whole pinned-grid column count, or the max. `DEFAULT_RAIL_WIDTH` (256) is
 * *not* in the list: it is an initial/persisted value, not a stop, and
 * previously made drags feel stuck at a ~2.5-column mid-width.
 *
 * #1683: the 4th column (394) is new. It was always geometrically available —
 * `MAX_PINNED_COLUMNS` counts it, and the grid grows a 4th track at ~387px —
 * it simply had no detent because the ladder stopped at three.
 */
export const RAIL_SNAP_POINTS: readonly number[] = [
  COLLAPSED_RAIL_WIDTH,
  ULTRACOMPACT_RAIL_WIDTH,
  ONE_COL_RAIL_WIDTH,
  TWO_COL_RAIL_WIDTH,
  THREE_COL_RAIL_WIDTH,
  FOUR_COL_RAIL_WIDTH,
  MAX_RAIL_WIDTH,
]

/**
 * #1683: the detent set for a rail with an EMPTY pin pool — 0 → 88 → 420.
 *
 * Every column detent is derived entirely from pinned-grid geometry: "the rail
 * width that exactly fits N pinned-grid columns". With nothing pinned,
 * `.os-fav-grid` renders `--bare` (no tiles, zero height) and those numbers
 * describe nothing the operator can see — a rail parked at 210px looks exactly
 * like one parked at 180px. So the free-track state keeps only the stops that
 * are meaningful in every state:
 *
 * - `COLLAPSED_RAIL_WIDTH` (0) — the divider-only pane;
 * - `ULTRACOMPACT_RAIL_WIDTH` (88) — the one-avatar-per-row tier;
 * - `MAX_RAIL_WIDTH` (420) — the rail's hard ceiling, still a stop.
 */
export const RAIL_UNPINNED_SNAP_POINTS: readonly number[] = [
  COLLAPSED_RAIL_WIDTH,
  ULTRACOMPACT_RAIL_WIDTH,
  MAX_RAIL_WIDTH,
]


/**
 * #1683: which detents the rail sticks to for a given pin count.
 *
 * THE RULE: the column detents are the widths that exactly fit
 * `1..min(pins, MAX_PINNED_COLUMNS)` columns — nothing more.
 *
 *     0 pins → [0, 88, 420]
 *     1 pin  → [0, 88, 118, 420]
 *     2 pins → [0, 88, 118, 210, 420]
 *     3 pins → [0, 88, 118, 210, 302, 420]
 *     4+     → [0, 88, 118, 210, 302, 394, 420]
 *
 * Three things are true in every state and are therefore in every set:
 * collapsed (0, the divider-only pane), ultra-compact (88, the one-avatar-per-row
 * tier — the operator explicitly wants it kept), and the ceiling (420, where the
 * free range ends and where `clampRailWidth` forbids going past).
 *
 * The free-tracking region between the topmost column detent and the ceiling is
 * NOT expressed here: it is expressed by the snap *threshold*
 * (`railSnapThresholdForPins`). Keeping it there means this function stays a
 * plain statement of "which widths are real stops", which is also exactly the
 * lane the arrow keys walk (`railSnapStep`) — drag and keyboard cannot drift
 * apart.
 *
 * The input is a *conservative* count (the stored pin list, a superset of the
 * tiles actually rendered) so it can only leave a detent in place when it does
 * not need to be, never drop one while a tile is on screen.
 */
export function railSnapPointsForPins(pinnedCount: number): readonly number[] {
  const points = [
    COLLAPSED_RAIL_WIDTH,
    ULTRACOMPACT_RAIL_WIDTH,
    ...railColumnDetents(pinnedCount),
  ]
  if (points[points.length - 1] !== MAX_RAIL_WIDTH) points.push(MAX_RAIL_WIDTH)
  return points
}

/**
 * #1683: the topmost RIGID detent for a pin count — the width above which the
 * rail free-tracks.
 *
 * Unpinned there is no grid at all, so the rigid region ends at the
 * ultra-compact tier and the entire rest of the range free-tracks. That is the
 * #1683 empty-pool behaviour, now reached through the same rule as the pinned
 * states instead of a parallel branch.
 */
export function topColumnDetent(pinnedCount: number): number {
  const columns = railColumnDetents(pinnedCount)
  return columns.length
    ? columns[columns.length - 1]
    : ULTRACOMPACT_RAIL_WIDTH
}

/**
 * #1683: the snap threshold for a dragged width — the #1262 guard, scoped.
 *
 * Returns `RAIL_DETENT_ALWAYS` (quantise every frame) at or below the topmost
 * column detent, and `RAIL_SNAP_THRESHOLD` (free-track) strictly above it.
 *
 * The reason it is safe to free-track up there is measured, not assumed — see
 * the `RAIL_DETENT_ALWAYS` note above. The reason it is NOT safe lower down is
 * measured too: a tile's column is `index % columns`, so any pin whose index
 * has reached `columns` jumps sideways on every track boundary the pointer
 * crosses. Widening past the topmost detent cannot do that, because the topmost
 * detent is by construction a width that seats every pin in row 1.
 */
export function railSnapThresholdForPins(
  width: number,
  pinnedCount: number = 1,
): number {
  if (pinnedCount <= 0) return RAIL_SNAP_THRESHOLD
  return width > topColumnDetent(pinnedCount)
    ? RAIL_SNAP_THRESHOLD
    : RAIL_DETENT_ALWAYS
}

/** #816: a right-docked rail's in-flow detents are its mirror image. */
function detentsForSide(railSide?: string, pinnedCount = 1): readonly number[] {
  const points = railSnapPointsForPins(pinnedCount)
  if (railSide !== 'right') return points
  const inFlow = points.filter((point) => point > COLLAPSED_RAIL_WIDTH)
  return [COLLAPSED_RAIL_WIDTH, ...inFlow.slice().reverse()]
}

/**
 * #1289: snap a dragged/keyboard width to the nearest detent for `railSide`.
 * Within `RAIL_SNAP_THRESHOLD` px the width sticks exactly to the detent;
 * outside it the width is returned unchanged (the edge still tracks the
 * pointer — no jitter or lock fighting the pointer). Below 1-column the two
 * collapse-zone detents (collapsed 0 / ultra-compact 96) are split by the
 * collapse threshold, so a release below the smallest snap point settles on
 * one of them rather than a free-floating value.
 *
 * #1683: `pinnedCount` picks the detent set (see `railSnapPointsForPins`).
 * It defaults to 1 — "the pinned grid is on screen" — so every pre-#1683
 * caller keeps the #1262 guard rather than silently losing it; the rail passes
 * the real count. `threshold` likewise defaults to the free-tracking slop, so a
 * caller that wants the wobble guard must say so — pass
 * `railSnapThresholdForPins(width, pinnedCount)`, which is what `useRailResize`
 * does on every drag frame and on release.
 */
export function snapRailWidthToPoints(
  width: number,
  railSide?: string,
  threshold: number = RAIL_SNAP_THRESHOLD,
  pinnedCount: number = 1,
): number {
  // Collapse zone (below one column) has just two detents — collapsed (0) and
  // ultra-compact (88). The collapse threshold is their frontier. Both are
  // real in every pin state, so this branch is pin-independent by design.
  if (width <= ONE_COL_RAIL_WIDTH) {
    return width < COLLAPSE_SNAP_THRESHOLD
      ? COLLAPSED_RAIL_WIDTH
      : ULTRACOMPACT_RAIL_WIDTH
  }
  const detents = detentsForSide(railSide, pinnedCount)
  // The rail has a hard ceiling in every state (`MAX_RAIL_WIDTH`, enforced by
  // `clampRailWidth` on the keyboard/load paths): free-tracking must not park
  // the edge past it just because no detent is near enough to snap to.
  const clamped = Math.min(width, MAX_RAIL_WIDTH)
  let nearest = detents[0]
  let best = Infinity
  for (const point of detents) {
    const distance = Math.abs(clamped - point)
    if (distance < best) {
      best = distance
      nearest = point
    }
  }
  if (best <= threshold) return nearest
  return clamped
}

/**
 * #1289: the detent a keyboard resize steps toward in `delta` direction.
 * #1683: same pin-dependent lane as `snapRailWidthToPoints` — the arrows walk
 * the detents the pin count earns, so a 2-pin rail never has to step through a
 * 3-column stop it cannot see. Because the free region above the topmost
 * column detent is bounded by the ceiling, and the ceiling is a detent, the
 * lane is closed: `ArrowRight` from the topmost column detent reaches the
 * ceiling and then stops. Keyboard and drag can reach the same widths.
 */
export function railSnapStep(
  width: number,
  delta: number,
  railSide?: string,
  pinnedCount: number = 1,
): number {
  const detents = detentsForSide(railSide, pinnedCount)
  const lane = detents.slice().sort((a, b) => a - b)
  if (delta > 0) {
    return lane.find((point) => point > width + 0.5) ?? lane[lane.length - 1]
  }
  for (let i = lane.length - 1; i >= 0; i -= 1) {
    if (lane[i] < width - 0.5) return lane[i]
  }
  return lane[0]
}

/** #1289: shared drag snap — detent nearest, with the collapse-zone pile. */
function snapDragWidth(
  width: number,
  viewportWidth?: number,
  pinnedCount: number = 1,
): number {
  if (width <= ONE_COL_RAIL_WIDTH) {
    // Collapse zone: only two detents live here — collapsed (0) and
    // ultra-compact (88). Their frontier is the collapse threshold (<52 →
    // shut); at or above it the rail is the ultra-compact avatar tier.
    if (width < COLLAPSE_SNAP_THRESHOLD) return COLLAPSED_RAIL_WIDTH
    return ULTRACOMPACT_RAIL_WIDTH
  }
  // Above one column: stick to the nearest pinned-grid detent within slop,
  // else clamp (and let the pointer keep tracking between detents).
  const clamped = clampRailWidth(width, viewportWidth)
  let nearest = clamped
  let best = Infinity
  for (const point of railSnapPointsForPins(pinnedCount)) {
    if (point <= ONE_COL_RAIL_WIDTH) continue
    const distance = Math.abs(clamped - point)
    if (distance < best) {
      best = distance
      nearest = point
    }
  }
  return best < RAIL_SNAP_THRESHOLD ? nearest : clamped
}

/**
 * #1083: on laptop viewports (<= 1440px), the rail defaults to a compact
 * one-column rail so horizontal chat space is preserved. On wider desktop
 * viewports (> 1440px), it defaults to fully expanded (256px).
 */
export const LAPTOP_MAX_WIDTH = 1440

export function defaultRailWidth(viewportWidth?: number): number {
  if (typeof viewportWidth === 'number' && viewportWidth > 0 && viewportWidth <= LAPTOP_MAX_WIDTH) {
    // #1083 regression guard (#1098): MIN_RAIL_WIDTH (68) is below
    // AVATAR_ONLY_THRESHOLD, so a laptop default *is* avatar-only mode
    // and avatar-only CSS hides every section header — the #1094 Dynamic
    // Subagents header disappeared for real users on laptops, not just
    // jsdom. Keep the default above the avatar-only line so headers and
    // footer labels render.
    //
    // The old floor (AVATAR_ONLY_THRESHOLD + 1) is above the
    // avatar-only line but *narrower than the rail's own chrome*: the
    // horizontal search row and the "Routines" footer label overflow a 97px
    // pane (label right edge 100.7px; the collapse control is pushed under
    // the resize handle). The laptop default is now the 1-column pinned-grid
    // detent — the narrowest non-avatar rail that seats that chrome.
    return Math.max(ONE_COL_RAIL_WIDTH, AVATAR_ONLY_THRESHOLD + 1)
  }
  return DEFAULT_RAIL_WIDTH
}

export function clampRailWidth(width: number, viewportWidth?: number): number {
  const max = viewportWidth ? Math.min(MAX_RAIL_WIDTH, Math.floor(viewportWidth * 0.45)) : MAX_RAIL_WIDTH
  return Math.min(Math.max(width, MIN_RAIL_WIDTH), max)
}

export function loadRailWidth(viewportWidth?: number): number {
  try {
    const raw = localStorage.getItem(RAIL_WIDTH_STORAGE_KEY)
    if (raw) {
      const parsed = Number(raw)
      if (!Number.isNaN(parsed)) {
        // #765: 0 is a legal persisted state (fully collapsed); anything
        // below it is garbage and normalizes to collapsed rather than
        // falling back to the default.
        if (parsed <= COLLAPSED_RAIL_WIDTH) return COLLAPSED_RAIL_WIDTH
        const clamped = clampRailWidth(parsed, viewportWidth)
        // AVATAR_ONLY_THRESHOLD < width < ONE_COL_RAIL_WIDTH is a dead
        // zone the snap physics never settles in (a drag releases to 88 or
        // 118): there the horizontal chrome is wider than the pane, so the
        // footer labels bleed past the rail edge. Lift a legacy value (e.g.
        // the old 96px/97px compact rails) to the one-column rail so
        // persisted compact rails stay legible.
        if (clamped > AVATAR_ONLY_THRESHOLD && clamped < ONE_COL_RAIL_WIDTH) {
          return ONE_COL_RAIL_WIDTH
        }
        return clamped
      }
    }
  } catch {}
  return defaultRailWidth(viewportWidth)
}

export function saveRailWidth(width: number): void {
  try {
    localStorage.setItem(RAIL_WIDTH_STORAGE_KEY, String(width))
  } catch {}
}

export function isAvatarOnlyWidth(width: number): boolean {
  return width <= AVATAR_ONLY_THRESHOLD
}

/**
 * #1712: how many columns the EXPAND control may open to.
 *
 * The owner narrowed this to 3 with an explicit "do not grow past 3 columns
 * wide" — 4+ pins wrap onto a second row instead of widening the pane. That is
 * deliberately NOT `MAX_PINNED_COLUMNS` (4, #1683): #1683 removed the ceiling
 * for the DRAG ladder, where 394px is a real geometric stop, while #1712 caps
 * the one-click expand. The two agree up to 3 and diverge above it, so the cap
 * states itself here rather than being inferred from the ladder.
 */
export const RAIL_EXPAND_MAX_COLUMNS = 3

/**
 * #1712: the width the expand control opens to for a given pin count —
 * `min(pins, RAIL_EXPAND_MAX_COLUMNS)` pinned-grid columns.
 *
 *     1 pin  → 1 column (118)
 *     2 pins → 2 columns (210)
 *     3 pins → 3 columns (302)
 *     4+     → 3 columns (302) — the 4th pin wraps onto the next row
 *
 * This is deliberately NOT `railSnapStep(ULTRACOMPACT, +1)`, which walks to the
 * *next* detent and therefore lands on one column for every pin count — the old
 * behaviour, where four pins expanded into a 1-wide pane and stacked four deep.
 * The ticket asks for the width that FITS the pins, not the next rung.
 *
 * Zero pins earn no column detent at all (#1683: nothing is on screen to seat),
 * so expand keeps the pre-#1712 viewport default there. Jumping straight to the
 * 420px ceiling would be a five-fold widening from one click with nothing to
 * show for it.
 */
export function railExpandWidthForPins(pinnedCount: number, viewportWidth?: number): number {
  const columns = Math.min(
    Math.max(Math.floor(pinnedCount) || 0, 0),
    RAIL_EXPAND_MAX_COLUMNS,
  )
  if (columns < 1) return defaultRailWidth(viewportWidth)
  return railWidthForColumns(columns)
}

/** #765: true only for the exact divider-only state. */
export function isFullyCollapsedWidth(width: number): boolean {
  return width <= COLLAPSED_RAIL_WIDTH
}

/**
 * #806: clamp plus an avatar-only snap; #765 adds the edge-collapse snap;
 * #1289 snaps to the pinned-grid detents (1/2/3 columns + avatar-only).
 * Dragging into the avatar-only zone snaps to the ultra-compact detent so
 * there is no floating dead zone; dragging below the collapse threshold
 * snaps fully shut so the edge is a firm detent, not a fight. Detents nearer
 * than `RAIL_SNAP_THRESHOLD` win first; between detents the width is
 * continuous (the edge still tracks the pointer).
 */
export function snapRailWidth(
  width: number,
  viewportWidth?: number,
  pinnedCount: number = 1,
): number {
  return snapDragWidth(width, viewportWidth, pinnedCount)
}
