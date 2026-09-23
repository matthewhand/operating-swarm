/**
 * #689 — pinned team (multi-agent) seats render **exactly one avatar plus
 * the +N counter**. The graduated two-face stack (#523's recency-ordered
 * graduation) is superseded: at pin size the second face reads as a second
 * agent, not a depth cue. #689 is the authority on the final spec.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

describe('#689 pinned team tile: single face + +N', () => {
  const tsx = readFileSync(join(process.cwd(), 'src/components/AgentSidebar.tsx'), 'utf8')

  it('no longer renders the graduated multi-face stack branch', () => {
    expect(tsx).not.toContain('pin-team-avatar-stack')
    // The recency graduation is gone from the pin render — only the single
    // face and the remainder chip remain.
    expect(tsx).not.toMatch(/pinTeamStackFaces\.map/)
  })

  it('keeps the single face and the +N remainder chip', () => {
    expect(tsx).toContain('data-testid="pin-team-face"')
    expect(tsx).toContain('data-testid="pin-team-remainder"')
  })

  it('#689 supersedes #523/#57/#398 multi-face pin stacks (doc note present)', () => {
    expect(tsx).toMatch(/#689[^\n]*supersedes|#689:\s*one face/i)
  })
})
