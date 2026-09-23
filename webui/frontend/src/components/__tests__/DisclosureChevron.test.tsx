import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DisclosureChevron } from '../DisclosureChevron'
import { CompactSummaryCard } from '../CompactSummaryCard'
import { SystemPreloadPill } from '../SystemPreloadPill'

const read = (rel: string) => readFileSync(join(process.cwd(), rel), 'utf8')

describe('DisclosureChevron (#557)', () => {
  it('points right when closed and down when open', () => {
    const { container, rerender } = render(<DisclosureChevron expanded={false} />)
    expect(container.querySelector('svg.lucide-chevron-right')).toBeTruthy()
    expect(container.querySelector('svg.lucide-chevron-down')).toBeNull()

    rerender(<DisclosureChevron expanded={true} />)
    expect(container.querySelector('svg.lucide-chevron-down')).toBeTruthy()
    expect(container.querySelector('svg.lucide-chevron-right')).toBeNull()
  })

  it('stays decorative — the trigger keeps aria-expanded', () => {
    const { container } = render(<DisclosureChevron expanded={false} />)
    expect(container.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true')
  })
})

describe('Summary chip chevron direction (#557)', () => {
  it('a collapsed Summary points right', () => {
    const { container } = render(<CompactSummaryCard body="digest" defaultExpanded={false} />)
    expect(container.querySelector('svg.lucide-chevron-right')).toBeTruthy()
  })

  it('an open Summary points down, never up via a rotated glyph', () => {
    const { container } = render(<CompactSummaryCard body="digest" defaultExpanded />)
    expect(container.querySelector('svg.lucide-chevron-down')).toBeTruthy()
    expect(container.querySelector('svg[class*="rotate-180"]')).toBeNull()
  })
})

describe('System preload pill chevron direction (#557)', () => {
  it('collapsed points right, open points down', () => {
    const closed = render(<SystemPreloadPill text="hello there" />)
    expect(closed.container.querySelector('svg.lucide-chevron-right')).toBeTruthy()
    closed.unmount()

    const open = render(<SystemPreloadPill text="hello there" defaultExpanded />)
    expect(open.container.querySelector('svg.lucide-chevron-down')).toBeTruthy()
  })
})

describe('no disclosure re-implements the chevron (#557)', () => {
  const DISCLOSURE_SITES = [
    'src/components/CompactSummaryCard.tsx',
    'src/components/SystemPreloadPill.tsx',
    'src/components/SubagentFanOutBlock.tsx',
    'src/components/RailSectionHeader.tsx',
  ]

  it.each(DISCLOSURE_SITES)('%s shares the component and never rotates a chevron', (rel) => {
    const src = read(rel)
    expect(src).toContain('DisclosureChevron')
    expect(src).not.toMatch(/rotate-180/)
    expect(src).not.toMatch(/ChevronUp/)
  })
})
