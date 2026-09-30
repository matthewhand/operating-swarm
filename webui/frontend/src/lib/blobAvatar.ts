/**
 * Deterministic Blobs avatar spec from an agent id.
 * Shape + solid colour + idle eye rest pose are hashed; no blueprint rewrite.
 */

export const BLOB_SHAPES = [
  'hexagon',
  'circle',
  'teardrop',
  'triangle',
  'pill',
  'cloud',
  'roundedRect',
  'diamond',
] as const

export type BlobShape = (typeof BLOB_SHAPES)[number]

/** Vibrant solids matching Matthew's Blobs spec shot. */
export const BLOB_COLORS = [
  '#7C5CBF',
  '#5CD65C',
  '#E23B3B',
  '#8B7BA8',
  '#3B82F6',
  '#E84A8A',
  '#DC3C3C',
  '#F5A623',
  '#14B8A6',
  '#A855F7',
  '#22C55E',
  '#F97316',
] as const

export interface BlobEyePose {
  /** Pair center X in the 40×40 viewBox. */
  x: number
  /** Pair center Y in the 40×40 viewBox. */
  y: number
  /** Rotation of the pair / gaze, degrees. */
  angle: number
}

export interface BlobSpec {
  shape: BlobShape
  color: string
  rest: BlobEyePose
  wanderPhase: [number, number, number]
}

/* -------------------------------------------------------------------------- *
 * #1717 — organic circle / pill silhouettes.
 *
 * `circle` and `pill` used to be a literal `<circle>` and a stadium `<rect>`.
 * Both read as machine-perfect: the circle has constant curvature and the pill
 * is two dead-straight edges welded to two identical caps. They are now closed
 * cubic-Bezier loops generated from a per-agent seed, so one side of the loop
 * reads flatter than the rest and the whole silhouette leans a little.
 *
 * The loop is a superellipse warped by two harmonics (the bend) plus a one-sided
 * flatten bias, then fitted so its bounding box is EXACTLY the old primitive's.
 * That fit is the clipping guard: whatever the warp does, the painted footprint
 * still spans 4.8..35.2 (circle) / 3.2..36.8 × 13.2..26.8 (pill), so a blob can
 * never grow into a neighbour's box or past the 40×40 viewBox edge.
 * -------------------------------------------------------------------------- */

/** viewBox edge length every blob silhouette is authored in. */
export const BLOB_VIEWBOX = 40

/**
 * Anchor samples per loop. 14 is the smallest count that still resolves the
 * flatten bias as a bend rather than a facet — the smallest rendered size is
 * 1.5rem, where a facet is a visible straight edge.
 */
const SILHOUETTE_SAMPLES = 14

/** Catmull-Rom → Bezier tension. 1 is uniform Catmull-Rom: smooth, no facets. */
const SILHOUETTE_TENSION = 1

/** Curve samples per segment when measuring the loop for the box fit. */
const SILHOUETTE_FIT_SAMPLES = 16

interface SilhouetteBox {
  cx: number
  cy: number
  /** Half-extent along x / y, in viewBox units. */
  rx: number
  ry: number
  /** Superellipse exponent. 2 is an ellipse; higher is squarer. */
  exponent: number
}

/**
 * Per-shape authoring boxes, which are the OLD primitives verbatim.
 *
 * `circle` — cx/cy 20, r 15.2. `pill` — x 3.2..36.8, y 13.2..26.8, rx 6.8. The
 * pill's exponent sits well below the 6 that a true stadium would need, which
 * is deliberate: a hard stadium is the read #1717 asks to break, so its caps
 * stay soft while the same bend/flatten family shapes the whole loop.
 */
const SILHOUETTE_BOXES: Partial<Record<BlobShape, SilhouetteBox>> = {
  circle: { cx: 20, cy: 20, rx: 15.2, ry: 15.2, exponent: 2 },
  pill: { cx: 20, cy: 20, rx: 16.8, ry: 6.8, exponent: 3.6 },
}

function signedPow(value: number, power: number): number {
  return Math.sign(value) * Math.abs(value) ** power
}

/**
 * One un-normalised point on the warped loop.
 *
 * `bend` is two harmonics at 2θ/3θ: low frequency, so the silhouette leans
 * instead of rippling. `bias` is a raised cosine that peaks on the flat side
 * and is zero more than ~90° away, which keeps the flatten local — a bias
 * applied all the way round would just shrink the whole blob.
 */
function organicPoint(
  angle: number,
  box: SilhouetteBox,
  phase: number,
  flatAngle: number,
  flatAmount: number,
  wobble: number,
): [number, number] {
  const exponent = 2 / box.exponent
  const ux = signedPow(Math.cos(angle), exponent)
  const uy = signedPow(Math.sin(angle), exponent)
  const bend =
    1 + wobble * Math.cos(2 * angle + phase) + 0.45 * wobble * Math.cos(3 * angle - phase)
  const bias = Math.max(0, Math.cos(angle - flatAngle)) ** 2
  const scale = bend * (1 - flatAmount * bias)
  return [box.cx + ux * box.rx * scale, box.cy + uy * box.ry * scale]
}

/** Uniform Catmull-Rom through a closed loop, as cubic Bezier control tuples. */
function toClosedCubics(points: [number, number][]): number[][] {
  const n = points.length
  const at = (i: number) => points[((i % n) + n) % n]
  const cubics: number[][] = []
  for (let i = 0; i < n; i += 1) {
    const [x, y] = at(i)
    const [px, py] = at(i - 1)
    const [nx, ny] = at(i + 1)
    const [ax, ay] = at(i + 2)
    cubics.push([
      x,
      y,
      x + ((nx - px) / 6) * SILHOUETTE_TENSION,
      y + ((ny - py) / 6) * SILHOUETTE_TENSION,
      nx - ((ax - x) / 6) * SILHOUETTE_TENSION,
      ny - ((ay - y) / 6) * SILHOUETTE_TENSION,
      nx,
      ny,
    ])
  }
  return cubics
}

function cubicPoint(cubic: number[], t: number): [number, number] {
  const u = 1 - t
  const a = u * u * u
  const b = 3 * u * u * t
  const c = 3 * u * t * t
  const d = t * t * t
  return [
    a * cubic[0] + b * cubic[2] + c * cubic[4] + d * cubic[6],
    a * cubic[1] + b * cubic[3] + c * cubic[5] + d * cubic[7],
  ]
}

/** Bounding box of the CURVE, not of the anchors. */
function curveBounds(cubics: number[][]): [number, number, number, number] {
  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity
  for (const cubic of cubics) {
    for (let step = 0; step <= SILHOUETTE_FIT_SAMPLES; step += 1) {
      const [x, y] = cubicPoint(cubic, step / SILHOUETTE_FIT_SAMPLES)
      if (x < minX) minX = x
      if (x > maxX) maxX = x
      if (y < minY) minY = y
      if (y > maxY) maxY = y
    }
  }
  return [minX, maxX, minY, maxY]
}

/**
 * Fit the finished curve to the authoring box.
 *
 * Fitting the ANCHORS is not enough: a Catmull-Rom segment bulges past its own
 * endpoints, so a loop fitted at the anchors still paints a fraction of a unit
 * outside the old primitive. Invisible next to a shape change on its own, but
 * it is exactly the kind of creep a rail of tightly packed avatars shows up, so
 * the fit is measured on the curve and run twice — pass one absorbs the bulge,
 * pass two absorbs what pass one's rescale reintroduced.
 */
function fitCurveToBox(cubics: number[][], box: SilhouetteBox): number[][] {
  let fitted = cubics
  for (let pass = 0; pass < 2; pass += 1) {
    const [minX, maxX, minY, maxY] = curveBounds(fitted)
    const scaleX = (box.rx * 2) / (maxX - minX)
    const scaleY = (box.ry * 2) / (maxY - minY)
    const shiftX = box.cx - ((minX + maxX) / 2) * scaleX
    const shiftY = box.cy - ((minY + maxY) / 2) * scaleY
    fitted = fitted.map((cubic) => [
      cubic[0] * scaleX + shiftX,
      cubic[1] * scaleY + shiftY,
      cubic[2] * scaleX + shiftX,
      cubic[3] * scaleY + shiftY,
      cubic[4] * scaleX + shiftX,
      cubic[5] * scaleY + shiftY,
      cubic[6] * scaleX + shiftX,
      cubic[7] * scaleY + shiftY,
    ])
  }
  return fitted
}

function cubicsToPath(cubics: number[][]): string {
  const parts: string[] = [`M${round2(cubics[0][0])} ${round2(cubics[0][1])}`]
  for (const cubic of cubics) {
    parts.push(
      `C${round2(cubic[2])} ${round2(cubic[3])} ${round2(cubic[4])} ${round2(cubic[5])} ${round2(cubic[6])} ${round2(cubic[7])}`,
    )
  }
  parts.push('Z')
  return parts.join(' ')
}

function round2(value: number): number {
  return Math.round(value * 100) / 100
}

/**
 * The organic `d` for a blob shape, or `null` when the shape keeps its existing
 * primitive (hexagon, teardrop, triangle, cloud, roundedRect, diamond).
 *
 * Deterministic per agent id, like shape/colour/pose: the same agent keeps the
 * same bend, and two agents never share one.
 */
export function blobSilhouettePath(shape: BlobShape, id: string): string | null {
  const box = SILHOUETTE_BOXES[shape]
  if (!box) return null
  const h = hashAgentId(`${id}:silhouette`)
  // Bounded so the flatten stays a lean rather than a dent, and so the loop
  // never self-intersects at 1.5rem.
  const phase = ((h >>> 4) % 628) / 100
  const flatAngle = (((h >>> 12) % 360) * Math.PI) / 180
  const flatAmount = 0.055 + ((h >>> 20) % 40) / 1000
  const wobble = 0.05 + ((h >>> 26) % 35) / 1000
  const anchors: [number, number][] = []
  for (let i = 0; i < SILHOUETTE_SAMPLES; i += 1) {
    const angle = (i / SILHOUETTE_SAMPLES) * Math.PI * 2
    anchors.push(organicPoint(angle, box, phase, flatAngle, flatAmount, wobble))
  }
  return cubicsToPath(fitCurveToBox(toClosedCubics(anchors), box))
}

export function hashAgentId(id: string): number {
  let hash = 2166136261
  const source = id.length > 0 ? id : 'agent'
  for (let i = 0; i < source.length; i += 1) {
    hash ^= source.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

export function blobSpecForAgent(id: string): BlobSpec {
  const h = hashAgentId(id)
  const eyes = hashAgentId(`${id}:eyes`)
  return {
    shape: BLOB_SHAPES[h % BLOB_SHAPES.length],
    color: BLOB_COLORS[(h >>> 8) % BLOB_COLORS.length],
    rest: {
      x: 17 + ((eyes >>> 4) % 70) / 10,
      y: 15.5 + ((eyes >>> 12) % 45) / 10,
      angle: -20 + ((eyes >>> 20) % 41),
    },
    wanderPhase: [
      ((eyes >>> 2) % 628) / 100,
      ((eyes >>> 10) % 628) / 100,
      ((eyes >>> 18) % 628) / 100,
    ],
  }
}

/** Slow wander — several-second periods, small travel. Not a seizure. */
export function wanderEyePose(spec: BlobSpec, elapsedSec: number): BlobEyePose {
  const [p1, p2, p3] = spec.wanderPhase
  const x = spec.rest.x + 3.1 * Math.sin(elapsedSec * 0.52 + p1)
  const y = spec.rest.y + 2.2 * Math.sin(elapsedSec * 0.37 + p2)
  const angle = spec.rest.angle + 12 * Math.sin(elapsedSec * 0.29 + p3)
  return {
    x: clamp(x, 14, 26),
    y: clamp(y, 13, 24),
    angle: clamp(angle, -28, 28),
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}
