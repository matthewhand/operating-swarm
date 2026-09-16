import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import BeeAvatar from '../BeeAvatar'
import {
  BEE_ACCESSORIES,
  BEE_VARIANTS,
  beeSpecForAgent,
  isFaceBeeVariant,
  type BeeVariant,
} from '../../lib/beeAvatar'

function findId(variant: BeeVariant): string {
  for (let i = 0; i < 240; i += 1) {
    const id = `bee-pack-${i}`
    if (beeSpecForAgent(id).variant === variant) return id
  }
  throw new Error(`no agent hashed to ${variant}`)
}

describe('BeeAvatar pack', () => {
  it('paints every variant with googly eyes and accessory chrome', () => {
    for (const variant of BEE_VARIANTS) {
      const id = findId(variant)
      const spec = beeSpecForAgent(id)
      const { container, unmount } = render(<BeeAvatar agentId={id} />)
      const svg = container.querySelector('svg[data-avatar-theme="bee"]')
      expect(svg).toHaveAttribute('data-bee-variant', variant)
      expect(svg).toHaveAttribute('data-bee-accent', spec.accent)
      expect(svg).toHaveAttribute('data-bee-accessory', spec.accessory)
      expect(svg).toHaveAttribute('data-bee-gaze', spec.gaze)
      expect(svg?.querySelector('[data-googly="true"]')).toBeInTheDocument()
      expect(BEE_ACCESSORIES).toContain(svg?.getAttribute('data-bee-accessory'))
      if (isFaceBeeVariant(variant) && spec.accessory !== 'none') {
        expect(svg?.querySelector(`.os-bee-accessory--${spec.accessory}`)).toBeInTheDocument()
      }
      unmount()
    }
  })

  it('keeps locked side-on and face-only ids as first-class variants', () => {
    expect(BEE_VARIANTS[0]).toBe('side-on')
    expect(BEE_VARIANTS[1]).toBe('face-only')
    const side = render(<BeeAvatar agentId={findId('side-on')} />)
    expect(side.container.querySelector('svg')).toHaveAttribute('data-bee-variant', 'side-on')
    side.unmount()
    const face = render(<BeeAvatar agentId={findId('face-only')} />)
    expect(face.container.querySelector('svg')).toHaveAttribute('data-bee-variant', 'face-only')
    face.unmount()
  })
})
