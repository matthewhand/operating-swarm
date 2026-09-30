/**
 * Rail polish batch — one pin file for the six rail/chat asks that share the
 * sidepane surface:
 *
 * - #805 speech theme: avatar nudged down+left toward the bubble tail
 * - #806 divider snap: avatar-only zone snaps to MIN_RAIL_WIDTH, no dead zone
 * - #817 team avatars: exactly one face + universal `+N` in every rail state
 * - #820 pinned + hidden rows align with the scroller's scrollbar gutter
 * - #824 disabled `+` menu items must not light up on hover
 * - #825 pinned grid sits below the search divider, not touching it
 * - #826 "Hidden Bots" copy is now "Hidden Agents" (with truncation)
 * - #829 pinned tiles are fixed squares with a constant badge offset
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const src = (p: string) => readFileSync(join(__dirname, '..', '..', p), 'utf8')
const css = () => src('index.css')
const sidebar = () =>
  src('components/AgentSidebar.tsx') + src('components/sidebar/rowsRender.tsx') // #856 slice G: row renderers moved verbatim
// #856 slice C: the drag handlers moved to the sidebar's resize hook.
const sidebarResizeHook = () => src('components/sidebar/useRailResize.ts')

function ruleBlock(text: string, selector: string): string {
  const at = text.indexOf(selector)
  if (at === -1) return ''
  const open = text.indexOf('{', at)
  const close = text.indexOf('}', open)
  return text.slice(open, close)
}

describe('#805 speech theme avatar offset', () => {
  it('nudges the assistant avatar down and left toward the bubble tail', () => {
    const block = ruleBlock(css(), '[data-bubble-theme="speech"] .chat-start:has(.chat-image) .chat-image')
    expect(block).toMatch(/transform:\s*translate\(-0\.25rem,\s*0\.25rem\)/)
  })
})

describe('#806 divider snap at the avatar-only threshold', () => {
  it('snaps into the avatar zone to the ultra-compact detent, leaves wider rails alone', async () => {
    // #1289 supersedes the old MIN_RAIL_WIDTH snap: the ultra-compact
    // (avatar-only) tier is its own detent = AVATAR_ONLY_THRESHOLD (88, #1350).
    const { snapRailWidth, ULTRACOMPACT_RAIL_WIDTH, AVATAR_ONLY_THRESHOLD } = await import('../railResize')
    expect(ULTRACOMPACT_RAIL_WIDTH).toBe(AVATAR_ONLY_THRESHOLD)
    expect(snapRailWidth(AVATAR_ONLY_THRESHOLD)).toBe(ULTRACOMPACT_RAIL_WIDTH)
    expect(snapRailWidth(AVATAR_ONLY_THRESHOLD - 10)).toBe(ULTRACOMPACT_RAIL_WIDTH)
    // 97 sits within the 14px slop of the 88 detent → sticks to it.
    expect(snapRailWidth(AVATAR_ONLY_THRESHOLD + 1)).toBe(ULTRACOMPACT_RAIL_WIDTH)
    // Far outside every detent's slop → continuous, pointer keeps tracking.
    expect(snapRailWidth(160)).toBe(160)
    expect(snapRailWidth(1000, 800)).toBe(360) // viewport clamp still applies
  })

  it('the sidebar drag handlers use the snapping clamp', () => {
    // #856 slice C: the drag handlers live in sidebar/useRailResize.ts; the
    // sidebar consumes them via useRailResize.
    // #1289: the drag now snaps to the pinned-grid detents.
    expect(sidebarResizeHook()).toMatch(/snapRailWidthToPoints\(/)
    expect(sidebar()).toMatch(/useRailResize\(/)
  })
})

describe('#817 one team face + universal +N', () => {
  it('railTeamStackLayout always returns a single face and the remainder', async () => {
    const { railTeamStackLayout } = await import('../avatarStack')
    const faces = [
      { id: 'a', startedAt: 3 },
      { id: 'b', startedAt: 2 },
      { id: 'c', startedAt: 1 },
    ]
    for (const collapsed of [true, false]) {
      const layout = railTeamStackLayout(faces, collapsed)
      expect(layout.faces).toHaveLength(1)
      expect(layout.faces[0].id).toBe('a')
      expect(layout.remainder).toBe(2)
    }
    const solo = railTeamStackLayout([faces[0]], false)
    expect(solo.remainder).toBe(0)
  })

  it('the wide rail no longer renders mini faces and the collapsed rail keeps the +N sticker', () => {
    const tsx = sidebar()
    expect(tsx).not.toMatch(/os-team-face__mini/)
    // collapsed branch carries the live remainder, not a hardcoded 0
    expect(tsx).not.toMatch(/data-remainder="0"/)
    expect(tsx).toMatch(/os-team-face__remainder/)
  })
})

describe('#1261 scrollbar gutter is owned by the scroll container', () => {
  // #1261 supersedes #820: the hand-tuned `--os-rail-gutter` padding was
  // *permanent* dead space — it reserved a gutter whether or not the rail
  // overflowed, and never shift-compensated when the scrollbar appeared. The
  // contract is now that the scroll container alone reserves the gutter with
  // `scrollbar-gutter: stable`, and the compensating padding/margin are gone.
  // jsdom computes no layout, so this keys off the stylesheet contract.
  it('reserves the gutter on .os-rail-scroller instead of padding the rows', () => {
    const text = css()
    expect(text).not.toMatch(/--os-rail-gutter:/)
    expect(ruleBlock(text, '.os-rail-scroller {')).toMatch(/scrollbar-gutter:\s*stable/)
    expect(ruleBlock(text, '.os-fav-grid {')).not.toMatch(/padding-right:\s*var\(--os-rail-gutter\)/)
    expect(ruleBlock(text, '.os-hidden-bots {')).not.toMatch(/margin-right:\s*calc\(0\.5rem \+ var\(--os-rail-gutter/)
  })

  it('reclaims the gutter in avatar-only mode, where the rail is narrowest', () => {
    const text = css()
    const avatarOnly = text.slice(text.indexOf('.os-agent-sidebar--avatar-only'))
    expect(avatarOnly).toMatch(/avatar-only[^{]*\.os-rail-scroller[^{]*\{[^}]*scrollbar-gutter:\s*auto/)
  })
})

describe('#824 disabled + menu items never highlight on hover', () => {
  it('suppresses the hover background for aria-disabled items', () => {
    const block = ruleBlock(css(), '.os-plus-menu__item[aria-disabled')
    expect(block).toMatch(/background:\s*transparent/)
  })
})

describe('#825 pinned grid clears the search divider', () => {
  it('keeps a top margin on .os-fav-grid', () => {
    expect(ruleBlock(css(), '.os-fav-grid {')).toMatch(/margin:\s*0\.35rem 0\.75rem 0\.5rem/)
  })
})

describe('#826 Hidden Agents copy', () => {
  it('the sidebar no longer says "Hidden Bots"', () => {
    expect(sidebar()).not.toMatch(/Hidden Bots/)
    expect(sidebar()).toMatch(/Hidden Agents/)
  })
})

describe('#829 pinned tiles are squares', () => {
  it('square floor + left-anchored fixed tracks + constant badge anchor', () => {
    const text = css()
    // #1071: the square is a floor now (min-height), not a hard clamp.
    expect(ruleBlock(text, '.os-fav-tile {')).toMatch(/width:\s*5\.25rem/)
    // Left-anchored, not centred: centring made a tile's x a function of the
    // container width, so tiles slid sideways on every resize pixel and jumped
    // on each 1->2->3 column change. `scripts/measure-pinned-grid.mjs` measured
    // 70 distinct x values across an 88..420 sweep with `center`, and zero
    // movement with `start`. jsdom cannot catch this — it has no layout engine.
    expect(ruleBlock(text, '.os-fav-grid {')).toMatch(/justify-content:\s*start/)
  })
})

describe('#902 pinned tile geometry is width-independent', () => {
  it('tiles are fixed-width squares that may grow vertically for their label', () => {
    const tile = ruleBlock(css(), '.os-fav-tile {')
    // fixed square size — the vertical dimension must not derive from the
    // fluid column width. (#934 widened 4.5rem → 5.25rem for the label.)
    // #1071/#1074: height is now a *floor* (min-height), not a clamp — a
    // two-line name gets its full second line instead of being cut off.
    expect(tile).toMatch(/width:\s*5\.25rem/)
    expect(tile).toMatch(/min-height:\s*5\.25rem/)
    expect(tile).not.toMatch(/(^|[^-])height:\s*5\.25rem/)
    expect(tile).not.toMatch(/aspect-ratio/)
    // #1262 revert: the tile centres in its fixed track — the fixed-width
    // track (not a fluid 1fr column) is what keeps rail resizes stable.
    expect(tile).toMatch(/justify-self:\s*center/)
    expect(tile).toMatch(/flex:\s*0 0 auto/)
  })

  it('grid uses fixed auto-fill tracks instead of fluid columns', () => {
    // Left-anchored so a column-count change only appends/removes tracks at the
    // trailing edge; `center` made every tile's x depend on container width.
    expect(ruleBlock(css(), '.os-fav-grid {')).toMatch(/justify-content:\s*start/)
    // a fixed tile width makes the container-query column churn cosmetic only
    expect(css()).toMatch(/@container \(max-width: 200px\)/)
  })
})

describe('#934 pinned tile labels are readable', () => {
  it('tiles give the label room: wider fixed square, not the old 4.5rem cramp', () => {
    const tile = ruleBlock(css(), '.os-fav-tile {')
    // The old 4.5rem square clipped most agent names mid-word. The tile is
    // still a fixed square (#902 doctrine), just one sized for its content.
    expect(tile).toMatch(/width:\s*5\.25rem/)
    expect(tile).toMatch(/min-height:\s*5\.25rem/)
    expect(tile).not.toMatch(/width:\s*4\.5rem/)
  })

  it('the label wraps to two lines with ellipsis instead of one hard clip', () => {
    const name = ruleBlock(css(), '.os-fav-tile__name {')
    expect(name).toMatch(/display:\s*-webkit-box/)
    expect(name).toMatch(/-webkit-line-clamp:\s*2/)
    expect(name).toMatch(/-webkit-box-orient:\s*vertical/)
    expect(name).toMatch(/overflow:\s*hidden/)
    // #1071: long words wrap instead of overflowing the clamp box
    expect(name).toMatch(/word-break:\s*break-word/)
    // a single clipped line is the bug
    expect(name).not.toMatch(/white-space:\s*nowrap/)
  })
})

describe('#1071/#1074 pinned tiles fit their labels and their rail', () => {
  it('the second line of a wrapped name is never clipped (dynamic tile height)', () => {
    const tile = ruleBlock(css(), '.os-fav-tile {')
    // vertical budget math from #1074: 5.25rem fixed height left 17.6px for
    // a 26.9px two-line label. min-height lets the tile grow instead.
    expect(tile).toMatch(/min-height:\s*5\.25rem/)
    expect(tile).not.toMatch(/(^|[^-])height:/)
  })

  it('avatar-only tiles shrink to the 68px rail, not the 84px square', () => {
    const tile = ruleBlock(
      css(),
      '.os-agent-sidebar--avatar-only .os-fav-tile {'
    )
    expect(tile).toMatch(/width:\s*auto/)
    expect(tile).not.toMatch(/width:\s*5\.25rem/)
  })
})

describe('#1075 avatar-only search chrome stays inside the sidebar', () => {
  it('the stacked search+add row grows to fit instead of centring into negative coordinates', () => {
    const row = ruleBlock(
      css(),
      '.os-agent-sidebar--avatar-only .os-rail-search-row {'
    )
    // #764 stacks the trigger and Add button vertically; their combined
    // 76px exceeds the 3.5rem chrome strip, so the fixed strip height
    // centred them into y<0 (clipping the search icon). The row now sizes
    // to its content with the chrome height as the floor.
    expect(row).toMatch(/height:\s*auto/)
    expect(row).toMatch(/min-height:\s*var\(--os-top-chrome-h\)/)
  })

  it('ultra-compact search trigger is a 2.25rem circle like the Add agent button', () => {
    const search = ruleBlock(css(), '.os-agent-sidebar--avatar-only .os-rail-search {')
    expect(search).toMatch(/width:\s*2\.25rem/)
    expect(search).toMatch(/height:\s*2\.25rem/)
    expect(search).toMatch(/border-radius:\s*999px/)
    expect(search).toMatch(/padding:\s*0/)
  })
})

describe('#1067 footer icons share one vertical axis', () => {
  it('avatar-only: the server button centres like Teams/Plugins/Routines above it', () => {
    const btn = ruleBlock(
      css(),
      '.os-agent-sidebar--avatar-only .os-rail-footer-btn {'
    )
    // The hostname icon button kept `flex w-full px-1` and stayed left-anchored
    // (13.5px drift vs the centred column). It must centre too.
    expect(btn).toMatch(/justify-content:\s*center/)
    expect(btn).toMatch(/padding-inline:\s*0/)
  })

  it('expanded: the server icon matches the 16px icon column of the nav rows', () => {
    const sidebarSrc = sidebar()
    // the server button drops its bespoke h-5 w-5 / h-3.5 sizing
    expect(sidebarSrc).not.toMatch(/os-rail-hostname-icon[^"']*btn-square h-5 w-5/)
    expect(sidebarSrc).toMatch(/os-rail-hostname-icon[^"']*h-4 w-4/)
  })
})

describe('#1068 hostname row shares the footer rhythm', () => {
  it('hostname typography matches the footer nav rows (text-sm scale)', () => {
    // line-anchored: the avatar-only `.os-rail-hostname {` (display:none)
    // appears earlier and contains the same substring.
    const host = ruleBlock(css(), '\n.os-rail-hostname {')
    expect(host).toMatch(/font-size:\s*0\.875rem/)
  })

  it('no extra top margin — padding rhythm comes from the footer container', () => {
    const row = ruleBlock(css(), '.os-rail-hostname-row {')
    expect(row).not.toMatch(/margin-top/)
  })

  it('the update chrome aligns its right edge with the nav rows\' padding', () => {
    const chrome = ruleBlock(css(), '.os-rail-update-chrome {')
    expect(chrome).toMatch(/margin-inline-end:\s*0\.25rem/)
  })
})
