/**
 * Sample a closed cubic-Bezier `d` so a test can make claims about the painted
 * geometry — bounding box, simple (non-self-intersecting) outline, symmetry —
 * instead of string-matching the path.
 *
 * jsdom has no layout engine, so `getBBox()` is not an option and a DOM test can
 * only assert that a `d` exists. These helpers let the unit tests assert the
 * geometry itself; the real-renderer proof for #1717 (dark mode, path-in-frame,
 * sidebar and floating-badge sizes) is `scripts/capture-1717-organic-blobs.mjs`.
 */

export interface Point {
  x: number
  y: number
}

export type Cubic = [Point, Point, Point, Point]

/** Parse `M x y (C …)* Z` into cubics. Throws on anything else, on purpose. */
export function parseClosedCubics(d: string): Cubic[] {
  const tokens = d.match(/[MCZ]|-?\d+(?:\.\d+)?/g) ?? []
  const cubics: Cubic[] = []
  let cursor = 0
  const num = () => {
    const value = Number(tokens[cursor])
    cursor += 1
    return value
  }
  if (tokens[cursor] !== 'M') throw new Error(`expected M, got ${tokens[cursor]}`)
  cursor += 1
  const start: Point = { x: num(), y: num() }
  let current = start
  while (cursor < tokens.length) {
    if (tokens[cursor] === 'Z') {
      cursor += 1
      break
    }
    if (tokens[cursor] !== 'C') throw new Error(`expected C, got ${tokens[cursor]}`)
    cursor += 1
    const c1: Point = { x: num(), y: num() }
    const c2: Point = { x: num(), y: num() }
    const end: Point = { x: num(), y: num() }
    cubics.push([current, c1, c2, end])
    current = end
  }
  if (cubics.length === 0) throw new Error('no cubics parsed')
  return cubics
}

function cubicAt([p0, p1, p2, p3]: Cubic, t: number): Point {
  const u = 1 - t
  const a = u * u * u
  const b = 3 * u * u * t
  const c = 3 * u * t * t
  const d = t * t * t
  return {
    x: a * p0.x + b * p1.x + c * p2.x + d * p3.x,
    y: a * p0.y + b * p1.y + c * p2.y + d * p3.y,
  }
}

/** Dense polyline approximation of the closed loop, endpoints excluded. */
export function sampleClosedPath(d: string, perCubic = 32): Point[] {
  const cubics = parseClosedCubics(d)
  const points: Point[] = []
  for (const cubic of cubics) {
    for (let i = 0; i < perCubic; i += 1) {
      points.push(cubicAt(cubic, i / perCubic))
    }
  }
  return points
}

export interface Bounds {
  minX: number
  maxX: number
  minY: number
  maxY: number
}

export function boundsOf(points: Point[]): Bounds {
  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity
  for (const { x, y } of points) {
    if (x < minX) minX = x
    if (x > maxX) maxX = x
    if (y < minY) minY = y
    if (y > maxY) maxY = y
  }
  return { minX, maxX, minY, maxY }
}

function cross(o: Point, a: Point, b: Point): number {
  return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x)
}

function segmentsCross(a1: Point, a2: Point, b1: Point, b2: Point): boolean {
  const d1 = cross(b1, b2, a1)
  const d2 = cross(b1, b2, a2)
  const d3 = cross(a1, a2, b1)
  const d4 = cross(a1, a2, b2)
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))
}

/**
 * True when no two non-adjacent edges of the sampled outline cross. A loop that
 * folds over itself is what "bendy" must never decay into: it would read as a
 * crease, not a lean.
 */
export function isSimpleLoop(points: Point[]): boolean {
  const n = points.length
  for (let i = 0; i < n; i += 1) {
    const a1 = points[i]
    const a2 = points[(i + 1) % n]
    for (let j = i + 2; j < n; j += 1) {
      if (i === 0 && j === n - 1) continue
      if (segmentsCross(a1, a2, points[j], points[(j + 1) % n])) return false
    }
  }
  return true
}

/** Signed area. Sign is the winding, magnitude is the painted area. */
export function signedArea(points: Point[]): number {
  let sum = 0
  for (let i = 0; i < points.length; i += 1) {
    const a = points[i]
    const b = points[(i + 1) % points.length]
    sum += a.x * b.y - b.x * a.y
  }
  return sum / 2
}

/**
 * Peak-to-peak spread of the loop's distance from `center`, normalised by the
 * shape's OWN half-extents.
 *
 * The normalisation is the whole point: a pill is 2.5× wider than it is tall, so
 * a bare-radius spread would report the pill's aspect ratio as if it were lean.
 * With rx/ry supplied, both a perfect circle and a perfect stadium score 0 and
 * the number is purely the #1717 lean.
 */
export function normalisedRadialSpread(
  points: Point[],
  center: Point,
  rx: number,
  ry: number,
): number {
  const radii = points.map(({ x, y }) => Math.hypot((x - center.x) / rx, (y - center.y) / ry))
  const mean = radii.reduce((sum, r) => sum + r, 0) / radii.length
  return (Math.max(...radii) - Math.min(...radii)) / mean
}

/**
 * Fourier amplitude of the loop's normalised radial profile at harmonic `n`.
 *
 * This is the metric that literally reads "one side is flatter". A circle, an
 * ellipse, a stadium and a superellipse are all mirror-symmetric about both
 * axes, so their ODD harmonics (n = 1, 3, 5 …) are identically zero. #1717
 * breaks that symmetry on purpose and the flatten bias is one-sided, so n = 1
 * is where the ticket shows up numerically — and it stays zero for every
 * pre-#1717 primitive, which is what makes it a regression guard rather than a
 * description of the new art.
 */
export function harmonicAmplitude(
  points: Point[],
  center: Point,
  n: number,
  rx: number,
  ry: number,
): number {
  let cosSum = 0
  let sinSum = 0
  let weight = 0
  for (const { x, y } of points) {
    const nx = (x - center.x) / rx
    const ny = (y - center.y) / ry
    const radius = Math.hypot(nx, ny)
    const angle = Math.atan2(ny, nx)
    cosSum += radius * radius * Math.cos(n * angle)
    sinSum += radius * radius * Math.sin(n * angle)
    weight += radius * radius
  }
  return weight === 0 ? 0 : Math.hypot(cosSum, sinSum) / weight
}

/**
 * Widest horizontal run of the outline sitting within `tolerance` (a fraction
 * of the box height) of the TOP edge, as a fraction of the box width.
 *
 * A stadium scores high here — that long straight flank is exactly what makes a
 * pill read as a pill — while an ellipse or a circle scores near zero. It is the
 * guard that stops the organic pill decaying into an oval.
 */
export function topEdgeRun(points: Point[], tolerance = 0.12): number {
  const bounds = boundsOf(points)
  const width = bounds.maxX - bounds.minX
  const height = bounds.maxY - bounds.minY
  const limit = bounds.minY + height * tolerance
  let widest = 0
  let runMin = Infinity
  let runMax = -Infinity
  for (const { x, y } of points) {
    if (y <= limit) {
      runMin = Math.min(runMin, x)
      runMax = Math.max(runMax, x)
    } else if (runMax > -Infinity) {
      widest = Math.max(widest, runMax - runMin)
      runMin = Infinity
      runMax = -Infinity
    }
  }
  if (runMax > -Infinity) widest = Math.max(widest, runMax - runMin)
  return width === 0 ? 0 : widest / width
}
