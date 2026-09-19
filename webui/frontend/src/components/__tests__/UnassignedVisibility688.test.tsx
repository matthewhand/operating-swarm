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
  const tsx = readFileSync(join(process.cwd(), 'src/components/AgentSidebar.tsx'), 'utf8')

  it('skips empty non-drag Unassigned blocks in the sections list', () => {
    const skip = tsx.match(/#688:[\s\S]{0,400}?return null/)?.[0] ?? ''
    expect(skip).toContain('isUnassignedSection(block.id)')
    expect(skip).toContain('block.rows.length === 0')
  })

  it('keeps the block renderable while a drag is in progress (drop target)', () => {
    const skip = tsx.match(/#688:[\s\S]{0,400}?return null/)?.[0] ?? ''
    expect(skip).toContain('!draggingId')
  })
})
