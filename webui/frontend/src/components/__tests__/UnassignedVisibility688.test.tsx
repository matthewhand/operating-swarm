/**
 * #688 — the **Unassigned** section never renders as a permanent empty block:
 * - with content → renders (like any section);
 * - emptied → hidden;
 * - while a drag is in progress → visible again as a drop target;
 * - "Move to → Unassigned" works regardless (context menu, not the block).
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

describe('#688 Unassigned section visibility', () => {
  const tsx = readFileSync(join(process.cwd(), 'src/components/AgentSidebar.tsx'), 'utf8') +
    readFileSync(join(process.cwd(), 'src/components/sidebar/RailSections.tsx'), 'utf8') // #856 slice I: fav-grid + section markup moved verbatim into sidebar/RailSections.tsx

  it('skips empty non-drag Unassigned blocks in the sections list', () => {
    const skip = tsx.match(/#688:[\s\S]{0,600}?return null/)?.[0] ?? ''
    expect(skip).toContain('isUnassignedSection(block.id)')
    expect(skip).toContain('block.rows.length === 0')
  })

  it('keeps the block renderable while a drag is in progress (drop target)', () => {
    const skip = tsx.match(/#688:[\s\S]{0,600}?return null/)?.[0] ?? ''
    expect(skip).toContain('!draggingId')
  })
})

describe('#729 Unassigned dead space & drop-zone reach', () => {
  const tsx = readFileSync(join(process.cwd(), 'src/components/AgentSidebar.tsx'), 'utf8') +
    readFileSync(join(process.cwd(), 'src/components/sidebar/RailSections.tsx'), 'utf8') // #856 slice I: fav-grid + section markup moved verbatim into sidebar/RailSections.tsx
  const css = readFileSync(join(process.cwd(), 'src/index.css'), 'utf8')

  it('idle scroller reserves no drag-era bottom gap (pb expands only mid-drag)', () => {
    expect(tsx).toMatch(/draggingId \? 'pb-16' : 'pb-4'/)
  })

  it('idle agent list keeps no 3rem min-height; dragging restores the affordance', () => {
    expect(tsx).toMatch(/os-agent-list--dragging/)
    const draggingRule = css.match(/\.os-agent-list--dragging\s*\{[^}]*\}/)
    expect(draggingRule).toBeTruthy()
    expect(draggingRule![0]).toContain('min-height')
    // the idle rule no longer forces 3rem of dead space
    const idleRule = css.match(/\.os-agent-list\s*\{[^}]*\}/)
    expect(idleRule).toBeTruthy()
    expect(idleRule![0]).not.toContain('min-height: 3rem')
  })

  it('empty Unassigned drop target is expanded (~2x) with a dashed affordance', () => {
    const rule = css.match(/\.os-rail-section-empty--unassigned\s*\{[^}]*\}/)
    expect(rule).toBeTruthy()
    expect(rule![0]).toContain('min-height')
    expect(rule![0]).toContain('dashed')
  })
})
