import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import BlobAvatar from '../BlobAvatar'
import { blobSilhouettePath, blobSpecForAgent } from '../../lib/blobAvatar'
import { boundsOf, sampleClosedPath } from '../../lib/__tests__/blobSilhouetteGeometry'

/**
 * #1717 - BlobAvatar must actually PAINT the organic loop.
 *
 * `lib/blobAvatar` can generate a beautiful organic path while the component
 * goes on rendering the old `<circle>`, and every geometry test in
 * `blobAvatarOrganic.test.ts` would still be green. These assertions are the
 * wiring guard: the `d` on screen is the `d` the generator produced.
 */

const ORGANIC_AGENTS = { circle: 'vera', pill: 'zed' } as const
const PRESERVED_AGENTS = { hexagon: 'stewie', triangle: 'reachy' } as const

describe('BlobAvatar organic silhouettes (#1717)', () => {
  it('renders circle and pill as a bendy path, never as a <circle> or stadium <rect>', () => {
    for (const [shape, agentId] of Object.entries(ORGANIC_AGENTS)) {
      const { container } = render(<BlobAvatar agentId={agentId} />)
      const svg = container.querySelector('svg[data-avatar-theme="blobs"]') as SVGSVGElement
      expect(svg.dataset.blobShape, `${agentId} must hash to ${shape}`).toBe(shape)
      expect(container.querySelector('.os-blob-body circle')).toBeNull()
      expect(container.querySelector('.os-blob-body rect')).toBeNull()
      const body = container.querySelector('.os-blob-body path') as SVGPathElement
      expect(body, `${shape} must paint a path`).toBeTruthy()
      expect(body.getAttribute('d')).toBe(blobSilhouettePath(shape as 'circle' | 'pill', agentId))
      expect(body.getAttribute('d')).toMatch(/^M-?[\d.]+ -?[\d.]+ C/)
      expect(body.getAttribute('d')).toMatch(/Z$/)
    }
  })

  it('leaves the other blob shapes on their original primitives', () => {
    for (const [shape, agentId] of Object.entries(PRESERVED_AGENTS)) {
      const { container } = render(<BlobAvatar agentId={agentId} />)
      const svg = container.querySelector('svg[data-avatar-theme="blobs"]') as SVGSVGElement
      expect(svg.dataset.blobShape, `${agentId} must hash to ${shape}`).toBe(shape)
      expect(blobSilhouettePath(shape as 'hexagon' | 'triangle', agentId)).toBeNull()
    }
  })

  it('keeps the animated wrappers the CSS depends on', () => {
    // `.os-blob-body` is what `transform-box: fill-box` + the jiggle keyframes
    // hang off, and `.os-blob-eyes` is what the wander keyframes hang off. If a
    // refactor moved the path out of `.os-blob-body` the silhouette would stop
    // breathing and the pill's 8deg jiggle would silently do nothing.
    for (const agentId of Object.values(ORGANIC_AGENTS)) {
      const { container } = render(<BlobAvatar agentId={agentId} active />)
      const body = container.querySelector('.os-blob-body') as SVGGElement
      expect(body.querySelector('path')).toBeTruthy()
      expect(container.querySelector('.os-blob-eyes')).toBeTruthy()
      expect(container.querySelector('svg')).toHaveAttribute('data-eye-state', 'active')
    }
  })

  it('paints the same footprint as the primitive it replaced, at every size class', () => {
    // The bbox is size-independent (it is in viewBox units), so this is really
    // asserting the loop survives the size prop untouched - a smaller badge is
    // exactly where an organic silhouette turns into an unreadable squiggle.
    const legacy = { circle: 15.2, pill: 16.8 }
    for (const size of ['xs', 'sm', 'md', 'lg', 'xl'] as const) {
      for (const [shape, agentId] of Object.entries(ORGANIC_AGENTS)) {
        const { container } = render(<BlobAvatar agentId={agentId} size={size} />)
        const body = container.querySelector('.os-blob-body path') as SVGPathElement
        const bounds = boundsOf(sampleClosedPath(body.getAttribute('d') as string))
        const halfWidth = (bounds.maxX - bounds.minX) / 2
        expect(halfWidth, `${shape}/${size}`).toBeCloseTo(legacy[shape as keyof typeof legacy], 1)
      }
    }
  })

  it('keeps the eyes inside the new silhouette for every agent', () => {
    // The rest pose is hashed independently of the shape, so an organic edge
    // that ate into the body would leave a blob staring through its own cheek.
    for (const agentId of ['vera', 'zed', 'reed', 'finn', 'suki', 'onyx']) {
      const { shape, rest } = blobSpecForAgent(agentId)
      const d = blobSilhouettePath(shape, agentId)
      if (!d) continue
      const points = sampleClosedPath(d)
      const bounds = boundsOf(points)
      expect(rest.x).toBeGreaterThan(bounds.minX)
      expect(rest.x).toBeLessThan(bounds.maxX)
      expect(rest.y).toBeGreaterThan(bounds.minY)
      expect(rest.y).toBeLessThan(bounds.maxY)
    }
  })
})
