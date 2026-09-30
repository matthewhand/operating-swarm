import { describe, expect, it } from 'vitest'
import { BLOB_SHAPES, BLOB_VIEWBOX, blobSilhouettePath, type BlobShape } from '../blobAvatar'
import {
  boundsOf,
  harmonicAmplitude,
  isSimpleLoop,
  normalisedRadialSpread,
  parseClosedCubics,
  sampleClosedPath,
  signedArea,
  topEdgeRun,
  type Point,
} from './blobSilhouetteGeometry'

/**
 * #1717 — the blob circle and pill are bendy closed loops, not a `<circle>` and
 * a stadium `<rect>`. These pin the four things that could silently regress:
 * the footprint (clipping), the loop's integrity (readability), the one-sided
 * asymmetry (the actual ticket), and the blast radius (nothing else moved).
 */

const CENTER = { x: 20, y: 20 }
type OrganicShape = 'circle' | 'pill'

/** Half-extents + the exact footprint of the primitives the loops replaced. */
const LEGACY: Record<OrganicShape, { rx: number; ry: number; bounds: Bounds }> = {
  circle: {
    rx: 15.2,
    ry: 15.2,
    bounds: { minX: 4.8, maxX: 35.2, minY: 4.8, maxY: 35.2 },
  },
  pill: {
    rx: 16.8,
    ry: 6.8,
    bounds: { minX: 3.2, maxX: 36.8, minY: 13.2, maxY: 26.8 },
  },
}

type Bounds = { minX: number; maxX: number; minY: number; maxY: number }

const ORGANIC: OrganicShape[] = ['circle', 'pill']
const PRESERVED: BlobShape[] = BLOB_SHAPES.filter((shape) => !ORGANIC.includes(shape as OrganicShape))

/** Agents spanning every shape bucket, so the preservation assertions bite. */
const AGENT_IDS = [
  'vera', 'zed', 'codey', 'stewie', 'reachy', 'dash', 'pip', 'lumen',
  'reed', 'finn', 'suki', 'onyx', 'rune', 'moss', 'iris', 'pike',
]

function loopFor(shape: OrganicShape, id: string): Point[] {
  const d = blobSilhouettePath(shape, id)
  if (!d) throw new Error(`${shape} has no organic path`)
  return sampleClosedPath(d)
}

describe('#1717: organic blob silhouettes', () => {
  it('hands circle and pill a closed cubic loop, and leaves every other shape primitive', () => {
    for (const shape of ORGANIC) {
      const d = blobSilhouettePath(shape, 'vera')
      expect(d, `${shape} must have a path`).toBeTruthy()
      expect(d!.startsWith('M')).toBe(true)
      expect(d!.endsWith('Z')).toBe(true)
      expect(d!.match(/C/g)?.length, 'the bend comes from cubics, not straight edges').toBe(14)
    }
    for (const shape of PRESERVED) {
      expect(blobSilhouettePath(shape, 'vera'), `${shape} must keep its primitive`).toBeNull()
    }
  })

  it('paints inside the footprint the old <circle>/<rect> occupied, so nothing clips or crowds', () => {
    for (const shape of ORGANIC) {
      for (const id of AGENT_IDS) {
        const bounds = boundsOf(loopFor(shape, id))
        const legacy = LEGACY[shape].bounds
        // toBeCloseTo(.., 1) is a 0.05-unit window: the loop is fitted to the
        // curve, not the anchors, so a Catmull-Rom bulge cannot creep past it.
        expect(bounds.minX, `${shape}/${id} minX`).toBeCloseTo(legacy.minX, 1)
        expect(bounds.maxX, `${shape}/${id} maxX`).toBeCloseTo(legacy.maxX, 1)
        expect(bounds.minY, `${shape}/${id} minY`).toBeCloseTo(legacy.minY, 1)
        expect(bounds.maxY, `${shape}/${id} maxY`).toBeCloseTo(legacy.maxY, 1)
      }
    }
  })

  it('keeps the loop inside the 40x40 viewBox, so no ancestor can clip a blob', () => {
    for (const shape of ORGANIC) {
      for (const id of AGENT_IDS) {
        const { minX, maxX, minY, maxY } = boundsOf(loopFor(shape, id))
        expect(Math.min(minX, minY), `${shape}/${id}`).toBeGreaterThanOrEqual(0)
        expect(Math.max(maxX, maxY), `${shape}/${id}`).toBeLessThanOrEqual(BLOB_VIEWBOX)
      }
    }
  })

  it('keeps the outline a simple, non-degenerate loop for every agent', () => {
    for (const shape of ORGANIC) {
      const { bounds } = LEGACY[shape]
      for (const id of AGENT_IDS) {
        const points = loopFor(shape, id)
        expect(isSimpleLoop(points), `${shape}/${id} must not self-intersect`).toBe(true)
        // Same winding for every agent — a flipped loop renders inside-out under
        // a nonzero fill-rule.
        expect(signedArea(points), `${shape}/${id} winding`).toBeGreaterThan(0)
        // Area within a few percent of the old primitive's, which is what keeps
        // a 1.5rem badge reading as a full silhouette rather than a thin arc.
        const legacyArea = (bounds.maxX - bounds.minX) * (bounds.maxY - bounds.minY) * 0.9
        const ratio = Math.abs(signedArea(points)) / legacyArea
        expect(ratio, `${shape}/${id} area ratio`).toBeGreaterThan(0.8)
        expect(ratio, `${shape}/${id} area ratio`).toBeLessThan(1.05)
      }
    }
  })

  it('is asymmetric — the n=1 harmonic a circle or a stadium cannot have', () => {
    for (const shape of ORGANIC) {
      const { rx, ry } = LEGACY[shape]
      for (const id of AGENT_IDS) {
        const points = loopFor(shape, id)
        // A perfect circle / ellipse / stadium / superellipse is mirror
        // symmetric, so its odd harmonics are identically zero. This is the
        // ticket's "flatter on one side" in one number.
        expect(
          harmonicAmplitude(points, CENTER, 1, rx, ry),
          `${shape}/${id} must not be mirror-symmetric`,
        ).toBeGreaterThan(0.01)
        // …and it must not wobble so far that it stops reading as its family.
        expect(
          normalisedRadialSpread(points, CENTER, rx, ry),
          `${shape}/${id} leans too far`,
        ).toBeLessThan(0.35)
      }
    }
  })

  it('varies the lean per agent instead of stamping one template', () => {
    for (const shape of ORGANIC) {
      const { rx, ry } = LEGACY[shape]
      const leans = AGENT_IDS.map((id) => {
        const phase = harmonicAmplitude(loopFor(shape, id), CENTER, 1, rx, ry)
        return Math.round(phase * 1e5)
      })
      expect(new Set(leans).size, `${shape} must not share one silhouette`).toBe(AGENT_IDS.length)
    }
  })

  it('keeps the pill a pill — a long flank, not an oval', () => {
    for (const id of AGENT_IDS) {
      // A stadium's straight flank covers well over half the width; an ellipse
      // covers almost none. The organic pill must land in between, not at the
      // ellipse end.
      expect(topEdgeRun(loopFor('pill', id)), `${id} lost its pill flank`).toBeGreaterThan(0.35)
    }
  })

  it('keeps the circle a circle — it is not a lumpy potato', () => {
    for (const id of AGENT_IDS) {
      const { rx, ry } = LEGACY.circle
      const points = loopFor('circle', id)
      // Higher-order harmonics are what turn a circle into a star or a potato.
      // #1717 wants a LEAN, so they stay small.
      expect(harmonicAmplitude(points, CENTER, 4, rx, ry), `${id} n=4`).toBeLessThan(0.05)
      expect(harmonicAmplitude(points, CENTER, 5, rx, ry), `${id} n=5`).toBeLessThan(0.05)
    }
  })

  it('is deterministic per agent, and the two organic shapes are distinct generators', () => {
    for (const shape of ORGANIC) {
      expect(blobSilhouettePath(shape, 'vera')).toBe(blobSilhouettePath(shape, 'vera'))
      const paths = new Set(AGENT_IDS.map((id) => blobSilhouettePath(shape, id)))
      expect(paths.size).toBe(AGENT_IDS.length)
    }
    expect(blobSilhouettePath('circle', 'zed')).not.toBe(blobSilhouettePath('pill', 'zed'))
  })

  it('round-trips through the parser the geometry assertions depend on', () => {
    // Guards the parser: a silently truncated parse would make every geometry
    // assertion above vacuously true.
    const d = blobSilhouettePath('circle', 'vera') as string
    const cubics = parseClosedCubics(d)
    expect(cubics).toHaveLength(14)
    expect(cubics[0][0]).toEqual(cubics[cubics.length - 1][3])
    // The last segment must land back on the M point, so the `Z` closes a
    // coincident point and the outline has no notch where it wraps.
    const start = cubics[0][0]
    const last = cubics[cubics.length - 1][3]
    expect(Math.hypot(last.x - start.x, last.y - start.y)).toBeLessThan(0.05)
  })
})
