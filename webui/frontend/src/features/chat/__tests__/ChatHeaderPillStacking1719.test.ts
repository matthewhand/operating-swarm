/**
 * #1719 — the floating agent pill painted BEHIND the chat transcript.
 *
 * The stacking-context chain, which is the whole content of this file:
 *
 *   .os-chat                      flex column, no stacking context
 *     <header class="os-chat-header">
 *         backdrop-filter: blur()      <-- #1701's glass
 *         position: relative
 *         z-index: 30                  <-- THE FIX
 *         => creates a STACKING CONTEXT
 *            <div class="os-agent-pill">  position: absolute; z-index: 20
 *     <div class="os-chat-transcript">   position: relative; z-index: auto
 *
 * Before the fix, `.os-chat-header` had `z-index: auto`, so the band's
 * stacking context sat at level 0 of the nearest shared ancestor context while
 * `.os-chat-transcript` — a positioned sibling with `z-index: auto` — painted
 * in the same step, LATER in tree order. The transcript therefore painted over
 * the whole band, and the pill's `z-index: 20` never left the band's context:
 * it competed only with the band's other children (both `z-index: auto`). The
 * pill was unclickable in every control.
 *
 * `z-index` is scoped to a stacking context, so raising the PILL can never fix
 * this. The value has to live on the element that CREATES the context — the
 * band — which is exactly where it now lives, in the one shared `.os-chat-
 * header` rule rather than a per-control patch.
 *
 * WHY A PARSED-STYLESHEET TEST AND NOT A HIT TEST: `document.elementFromPoint`
 * needs a compositor and a layout engine, so the paint-order proof lives in
 * `scripts/measure-chat-chrome.mjs`, which mounts the real `ChatHeader` in
 * Chromium against a real `vite build` of this stylesheet and reads the
 * browser's own hit test. This file covers what jsdom CAN answer — that the
 * stacking contexts the fix depends on are the ones actually in the shipped
 * sheet — so the band cannot silently lose its `z-index` again.
 *
 * There is deliberately NO assertion of the form "the file contains the string
 * `z-index: 30`": a needle would pass just as happily if the number appeared
 * under an unrelated selector, or if the rule were later duplicated.
 */
import { describe, expect, it } from 'vitest'
import { declaration, declarations, rule } from '../../../lib/__tests__/helpers/cssRules'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const css = readFileSync(join(process.cwd(), 'src/index.css'), 'utf8')

const band = declarations(rule(css, '.os-chat-header'))

/**
 * Elements that create a stacking context without being positioned-then-
 * indexed. These are what trap a descendant's `z-index`.
 */
const STACKING_CONTEXT_TRIGGERS = [
  'backdrop-filter',
  'filter',
  'transform',
  'perspective',
  'mix-blend-mode',
  'isolation',
  'will-change',
  'contain',
  'mask',
  'clip-path',
]

describe('#1719 — the band stacks above the transcript it floats over', () => {
  it('gives the band a stacking level of its own', () => {
    // The band is `position: relative`, so a z-index here is honoured; without
    // one it is `auto` and its context loses to a later positioned sibling.
    expect(band.position).toBe('relative')

    const z = band['z-index']
    expect(z, '.os-chat-header declares no z-index, so the pill is trapped').toBeDefined()
    expect(z).not.toBe('auto')

    const level = Number(z)
    expect(Number.isFinite(level)).toBe(true)
    expect(level).toBeGreaterThan(0)
  })

  it('states the level on the ONE shared band rule, exactly once', () => {
    // #1719's acceptance: the band is shared chrome, so the fix belongs in its
    // single rule. A bespoke `.os-chat-header .os-agent-pill { z-index: … }`
    // would leave the band's own context at 0 and change nothing — the exact
    // trap the issue describes. So the band carries exactly one z-index, and
    // no descendant rule adds a second lever into the same context.
    const bandZ = Object.entries(declarations(rule(css, '.os-chat-header'))).filter(
      ([prop]) => prop === 'z-index',
    )
    expect(bandZ).toHaveLength(1)

    const descendants = [
      '.os-chat-header .os-agent-pill',
      '.os-chat-header__identity',
      '.os-chat-header__controls',
      '.os-chat-header__meter',
    ]
    for (const selector of descendants) {
      expect(
        declaration(css, selector, 'z-index'),
        `${selector} must not try to fix #1719 by index — it is trapped in the band's context`,
      ).toBeUndefined()
    }
  })

  it('rises above the transcript but stays under the rail resizer and overlays', () => {
    const bandLevel = Number(band['z-index'])

    // The transcript the pill hangs over must not be lifted past the band by a
    // rule of its own; if it ever is, the two would race and this file would
    // stop describing what the browser does.
    const transcriptLevel = declaration(css, '.os-chat-transcript', 'z-index')
    expect(transcriptLevel === undefined || Number(transcriptLevel) < bandLevel).toBe(true)

    // The rail's resize handle deliberately overlaps this pane by 8px
    // (#1147/#1309): its hit-zone MUST stay above the band or dragging the
    // rail breaks. This is the assertion that stops "fix #1719" from being
    // fixed by a huge number.
    const resizer = Number(declarations(rule(css, '.os-rail-resizer'))['z-index'])
    expect(bandLevel).toBeLessThan(resizer)

    // …and the pill keeps its own lower level for ordering against its
    // siblings INSIDE the band, which is the only thing that value ever did.
    const pillLevel = Number(declarations(rule(css, '.os-agent-pill'))['z-index'])
    expect(pillLevel).toBeGreaterThan(0)
    expect(bandLevel).toBeGreaterThan(pillLevel)
  })

  it('keeps the glass that created the stacking context in the first place', () => {
    // Removing the blur would "fix" the trap by deleting #1701. Assert the
    // backdrop is still declared on the same rule, so the two facts stay in one
    // place: this rule creates a stacking context AND declares the level that
    // resolves it.
    expect(band['backdrop-filter']).toBeTruthy()
    expect(band['backdrop-filter']).not.toBe('none')
  })

  it('does not add a stacking-context trigger the fix then has to undo', () => {
    // Every trigger in this list traps descendants exactly like the blur does.
    // The band is allowed exactly one of them — the one #1701 owns.
    const triggers = STACKING_CONTEXT_TRIGGERS.filter((p) => band[p])
    expect(triggers).toEqual(['backdrop-filter'])
  })
})
