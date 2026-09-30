/**
 * #1695 — the server / socket popup trigger's glyph in the rail footer's shared
 * control column.
 *
 * Measured in a real renderer (Playwright + the BUILT stylesheet served at
 * :8001) before changing anything, in BOTH rail modes and in both dock sides:
 *
 *   expanded rail (256px)  siblings: 16x16 glyph at x=16, optical centre x=24
 *                          trigger:  14x16 glyph at x=13, optical centre x=20
 *   avatar-only rail (88px) siblings + trigger all 16x16 on one axis
 *
 * Two real defects, both in the EXPANDED rail (the default):
 *   1. daisyUI's `.btn` keeps a 1px border even on `btn-ghost` (transparent,
 *      so invisible) — that turned the trigger's 1rem content box into 14px and
 *      squeezed the glyph from 16x16 to 14x16: the same icon, 12.5% narrower
 *      than every neighbour.
 *   2. the trigger is a 1rem SQUARE, so even un-squeezed its glyph centres at
 *      +0.5rem, while the sibling rows' glyphs start at their own `px-1`
 *      (0.25rem) and are 16px wide — optical centres at +0.75rem. The glyph sat
 *      0.25rem left of the icon column.
 *
 * Both fixes live in the ONE shared rule that owns this control
 * (`.os-rail-hostname-icon`) — not as a bespoke margin on the button — and the
 * vertical axis is deliberately untouched: `height`/`width`/`padding` stay
 * exactly as they were, so the row keeps centring the glyph on the same
 * centreline. The compact rail centres its pills instead of offsetting them, so
 * that mode resets the offset.
 */
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import AgentSidebar from '../AgentSidebar'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'
import { HIDDEN_AGENTS_STORAGE_KEY } from '../../lib/hiddenAgents'
import { declarations } from '../../lib/__tests__/helpers/cssRules'

const css = readFileSync(join(process.cwd(), 'src/index.css'), 'utf8')

/**
 * The body of the rule whose PRELUDE is exactly `selector`.
 *
 * `ruleBodies()` accepts a selector that is only the last compound of a longer
 * prelude (`.os-agent-sidebar--avatar-only .os-rail-hostname-row` matches a
 * `.os-rail-hostname-row` probe), and for these selectors the compact-rail
 * override appears FIRST in the sheet — so the strict anchor is what keeps this
 * test pointed at the base rule. The body is then read with the shared
 * `declarations()` parser, not by substring.
 */
function exactRuleBody(selector: string): string {
  const re = new RegExp(`^${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}[ \\t]*\\{`, 'm')
  const match = re.exec(css)
  if (!match) throw new Error(`no rule for ${selector}`)
  const open = css.indexOf('{', match.index)
  let depth = 0
  for (let i = open; i < css.length; i += 1) {
    if (css[i] === '{') depth += 1
    else if (css[i] === '}') {
      depth -= 1
      if (depth === 0) return css.slice(open + 1, i)
    }
  }
  throw new Error(`unbalanced rule for ${selector}`)
}

function ruleFor(selector: string): Record<string, string> {
  return declarations(exactRuleBody(selector))
}

function listResponse(data: unknown) {
  return { ok: true, status: 200, json: async () => ({ object: 'list', data }) } as Response
}

function mockFetch() {
  return vi.fn().mockImplementation(async (input: RequestInfo) => {
    const url = String(input)
    if (url.includes('/v1/preferences')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          object: 'user_preferences',
          principal: 'session:test',
          guest: true,
          empty: true,
          favourites: [],
          hidden_agents: [],
        }),
      } as Response
    }
    if (url.includes('blueprint')) return listResponse([])
    return listResponse([])
  })
}

function renderRail() {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1920 })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/chat']}>
        <AgentSidebar open onClose={() => undefined} onOpenSearch={() => undefined} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
  localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, '[]')
  vi.stubGlobal('fetch', mockFetch())
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('#1695 the styled rule is the one the rendered trigger carries', () => {
  it('the server/socket trigger is the shared footer control, glyph box included', async () => {
    renderRail()
    await screen.findByRole('navigation', { name: 'Agent list' })
    const trigger = screen.getByTestId('rail-server-icon')
    expect(trigger).toHaveAttribute('aria-label', 'Remote sessions')
    expect(trigger.className).toContain('os-rail-hostname-icon')

    // The three neighbours are the other half of the comparison: same footer,
    // same 1rem glyph, and they are what the trigger must line up with.
    const siblings = ['os-teams-button', 'os-plugins-button', 'os-calendar-button']
    for (const testid of siblings) {
      const node = screen.getByTestId(testid)
      expect(node.className).toContain('os-rail-footer-btn')
      expect(node.querySelector('svg')?.getAttribute('class')).toContain('h-4 w-4')
    }
    // The trigger asks for the same 1rem glyph box as the neighbours, so the
    // only thing that could shrink it is the button's own chrome.
    expect(trigger.querySelector('svg')?.getAttribute('class')).toContain('h-4 w-4')
    expect(within(trigger).queryByTestId('local-server-status-dot')).toBeNull()
  })
})

describe('#1695 the shared rule stops squeezing and re-centres the glyph', () => {
  it('drops the invisible .btn border that squeezed the glyph to 14x16', () => {
    const trigger = ruleFor('.os-rail-hostname-icon')
    // daisyUI `.btn` declares a 1px border width even on `btn-ghost`; with a
    // 1rem box that is a 14px content box, and the 1rem SVG shrinks into it.
    expect(trigger['border']).toBe('0')
    expect(trigger['border-width'], 'no leftover btn border width').toBeUndefined()
  })

  it('offsets the box by the siblings’ own 0.25rem padding so the centres meet', () => {
    const trigger = ruleFor('.os-rail-hostname-icon')
    // The sibling rows are `px-1` (0.25rem) full-width rows: their 1rem glyph
    // starts 0.25rem in. A 1rem square centres its glyph at 0.5rem instead, so
    // the square is offset by that same 0.25rem.
    expect(trigger['margin-left']).toBe('0.25rem')
  })

  it('leaves the vertical axis exactly as the #1244 contract pinned it', () => {
    const trigger = ruleFor('.os-rail-hostname-icon')
    expect(trigger['align-items']).toBe('center')
    expect(trigger['height']).toBe('1rem')
    expect(trigger['width']).toBe('1rem')
    expect(trigger['padding']).toBe('0')
    // The row still centres the control, and still owns the 2rem rhythm.
    const row = ruleFor('.os-rail-hostname-row')
    expect(row['align-items']).toBe('center')
    expect(row['height']).toBe('2rem')
    expect(row['padding']).toBe('0')
  })

  it('the compact rail centres its pills, so the offset is reset there', () => {
    const compact = ruleFor('.os-agent-sidebar--avatar-only .os-rail-icon-badge')
    expect(compact['margin-left']).toBe('0')
    // The compact pills are 1.9rem squares centred by the row.
    expect(compact['justify-content']).toBeUndefined()
    const compactRow = ruleFor('.os-agent-sidebar--avatar-only .os-rail-hostname-row')
    expect(compactRow['justify-content']).toBe('center')
    expect(compactRow['height']).toBe('2rem')
  })

  it('both rail modes still render the trigger after the rule change', async () => {
    renderRail()
    const trigger = await waitFor(() => screen.getByTestId('rail-server-icon'))
    expect(trigger).toBeInTheDocument()
    expect(trigger.className).toContain('os-rail-hostname-icon')
  })
})
