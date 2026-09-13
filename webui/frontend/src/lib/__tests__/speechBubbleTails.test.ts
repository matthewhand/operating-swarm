import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

/**
 * #166: the default chat look keeps the DaisyUI speech-bubble tail visible on
 * both sides — assistant bottom-left, user bottom-right — with symmetric room
 * so neither tail is clipped or neutralized.
 */
describe('Speech-bubble tails stay visible and symmetric (#166)', () => {
  const css = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')

  /** Every rule body for a selector, in source order. */
  function blocksFor(selector: string): string[] {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const re = new RegExp(`${escaped}\\s*\\{([^}]*)\\}`, 'g')
    const out: string[] = []
    let match: RegExpExecArray | null
    while ((match = re.exec(css)) !== null) {
      out.push(match[1] ?? '')
    }
    return out
  }

  /** The transcript rule that owns vertical clearance — i.e. the non-media base. */
  function transcriptBaseBlock(): string {
    const block = blocksFor('.os-chat-transcript').find((body) =>
      body.includes('scroll-padding-bottom'),
    )
    expect(block, 'missing base .os-chat-transcript rule').toBeTruthy()
    return block!
  }

  function paddingPair(block: string): [number, number] {
    const left = block.match(/padding-left:\s*([^;]+);/)
    const right = block.match(/padding-right:\s*([^;]+);/)
    expect(left?.[1]?.trim(), 'missing padding-left').toBeTruthy()
    expect(right?.[1]?.trim(), 'missing padding-right').toBeTruthy()
    return [parseFloat(left![1]!), parseFloat(right![1]!)]
  }

  it('reserves equal inline room on both sides of the transcript', () => {
    const [left, right] = paddingPair(transcriptBaseBlock())
    expect(left).toBe(right)
    // At least the 0.75rem tail width so a complete tail fits on either edge.
    expect(left).toBeGreaterThanOrEqual(0.75)
  })

  it('keeps the equal-room gutters at the sm breakpoint', () => {
    const start = css.indexOf('@media (min-width: 640px)')
    expect(start).toBeGreaterThanOrEqual(0)
    const [left, right] = paddingPair(css.slice(start, start + 400))
    expect(left).toBe(right)
    expect(left).toBeGreaterThanOrEqual(0.75)
  })

  it('draws a shared, mirrored tail for assistant (left) and user (right)', () => {
    const shared = css.match(
      /\.os-chat-transcript \.chat-start \.chat-bubble::before,\s*\.os-chat-transcript \.chat-end \.chat-bubble::before\s*\{([^}]*)\}/,
    )
    expect(shared, 'missing shared tail rule').toBeTruthy()
    const body = shared![1]!
    // Positive contract: the tail is actually painted and never neutralized.
    expect(body).toContain('content: ""')
    expect(body).toMatch(/background-color:\s*inherit/)
    expect(body).toMatch(/-webkit-mask-image:\s*var\(--mask-chat\)/)
    expect(body).toMatch(/mask-image:\s*var\(--mask-chat\)/)
    expect(body).not.toMatch(/display:\s*none/)
    expect(body).not.toMatch(/content:\s*none/)

    expect(css).toMatch(
      /\.os-chat-transcript \.chat-start \.chat-bubble::before\s*\{[^}]*inset-inline-start:\s*-0\.75rem[^}]*transform:\s*rotateY\(0\)/,
    )
    expect(css).toMatch(
      /\.os-chat-transcript \.chat-end \.chat-bubble::before\s*\{[^}]*inset-inline-start:\s*100%[^}]*transform:\s*rotateY\(180deg\)/,
    )
  })
})
