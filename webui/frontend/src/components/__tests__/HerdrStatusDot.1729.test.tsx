/**
 * #1729 — the Herdr status indicator, asserted on rendered DOM.
 *
 * Deliberately no source-text assertions: a test that greps the `.tsx` for a
 * literal passes whether or not the component works. Everything here reads the
 * rendered element, the accessible name, and the computed style the browser
 * resolved.
 */

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { HerdrStatusDot, herdrStatusCopy, useClearHerdrSeatOnOpen } from '../HerdrStatusDot'
import { parsedRules, type Decl } from './cssRules'
import {
  applyHerdrStatusFrame,
  resetHerdrStatusStore,
  type HerdrStatusFrame,
} from '../../lib/herdrStatus'
import { isAgentUnread, markAgentRead } from '../../lib/unreadAgents'

function frame(over: Partial<HerdrStatusFrame> = {}): HerdrStatusFrame {
  return {
    type: 'herdr_status',
    seat_id: 'herdr:w3:p1',
    target: 'w3:p1',
    status: 'waiting',
    ...over,
  }
}

function ClearProbe({ seatId, open }: { seatId: string; open: boolean }) {
  useClearHerdrSeatOnOpen(seatId, open)
  return <span data-testid="probe" />
}

describe('#1729 HerdrStatusDot', () => {
  beforeEach(() => {
    localStorage.clear()
    resetHerdrStatusStore()
  })
  afterEach(cleanup)

  describe('what renders', () => {
    it('renders nothing for a waiting-free status', () => {
      for (const status of ['unknown', 'idle', 'working'] as const) {
        const { container } = render(
          <HerdrStatusDot seatId="herdr:w3:p1" status={status} label="grok" />,
        )
        // Busy/idle/unknown are not this component's job — the rail animates
        // busy seats already, and an unjustified dot is worse than none.
        expect(container.querySelector('[data-testid="herdr-status-dot"]')).toBeNull()
        cleanup()
      }
    })

    it('renders a status element when the agent is waiting on a question', () => {
      render(<HerdrStatusDot seatId="herdr:w3:p1" status="waiting" label="grok" />)
      const dot = screen.getByTestId('herdr-status-dot')
      expect(dot).toBeInTheDocument()
      expect(dot.getAttribute('data-status')).toBe('waiting')
    })

    it('renders for a finished turn', () => {
      render(<HerdrStatusDot seatId="herdr:w3:p1" status="finished" label="grok" />)
      expect(screen.getByTestId('herdr-status-dot').getAttribute('data-status')).toBe(
        'finished',
      )
    })

    it('reads the live store when no status prop is given', () => {
      applyHerdrStatusFrame(frame({ status: 'blocked' }))
      render(<HerdrStatusDot seatId="herdr:w3:p1" label="grok" />)
      expect(screen.getByTestId('herdr-status-dot')).toBeInTheDocument()
    })

    it('renders nothing for a seat the store has never heard from', () => {
      const { container } = render(<HerdrStatusDot seatId="herdr:never-seen" label="?" />)
      expect(container.querySelector('[data-testid="herdr-status-dot"]')).toBeNull()
    })
  })

  describe('accessibility — the state is never colour-only', () => {
    it('announces itself as a live status region', () => {
      render(<HerdrStatusDot seatId="herdr:w3:p1" status="waiting" label="grok" />)
      const dot = screen.getByTestId('herdr-status-dot')
      expect(dot.getAttribute('role')).toBe('status')
      expect(dot.getAttribute('aria-live')).toBe('polite')
    })

    it('names the state in words, with the agent', () => {
      render(<HerdrStatusDot seatId="herdr:w3:p1" status="waiting" label="grok" />)
      const dot = screen.getByRole('status')
      // A screen reader gets the meaning, not "a small yellow circle".
      expect(dot.getAttribute('aria-label')).toBe('grok: waiting on you')
      expect(dot.getAttribute('title')).toBe('grok: waiting on you')
    })

    it('names a finished state differently from a waiting one', () => {
      render(<HerdrStatusDot seatId="herdr:w3:p1" status="finished" label="grok" />)
      expect(screen.getByRole('status').getAttribute('aria-label')).toBe('grok: Finished')
    })

    it('falls back to a generic name when no label is supplied', () => {
      render(<HerdrStatusDot seatId="herdr:w3:p1" status="waiting" />)
      expect(screen.getByRole('status').getAttribute('aria-label')).toBe(
        'Herdr agent: waiting on you',
      )
    })

    it('carries a visible glyph, not just a hue', () => {
      render(<HerdrStatusDot seatId="herdr:w3:p1" status="waiting" label="grok" />)
      // The glyph is the non-colour affordance: with all colour removed the
      // states must still be distinguishable.
      const glyph = screen.getByTestId('herdr-status-dot').querySelector(
        '.os-herdr-status-dot__glyph',
      )
      expect(glyph).not.toBeNull()
      expect(glyph?.textContent?.trim()).toBe('?')
      expect(glyph?.getAttribute('aria-hidden')).toBe('true')
    })

    it('gives the two states different glyphs', () => {
      render(<HerdrStatusDot seatId="herdr:w3:p1" status="waiting" label="grok" />)
      const waiting = screen
        .getByTestId('herdr-status-dot')
        .querySelector('.os-herdr-status-dot__glyph')?.textContent
      cleanup()
      render(<HerdrStatusDot seatId="herdr:w3:p1" status="finished" label="grok" />)
      const finished = screen
        .getByTestId('herdr-status-dot')
        .querySelector('.os-herdr-status-dot__glyph')?.textContent
      expect(waiting).not.toBe(finished)
    })
  })

  describe('the stylesheet the component depends on', () => {
    /**
     * Parse the real `index.css` into an AST and read declarations off the
     * rules that target this component. Parsed, not grepped: a literal search
     * for `--waiting` would pass on a comment and fail on a reformat.
     */
    const rules = parsedRules()

    it('parses the dot rules out of the real stylesheet', () => {
      // If the selector vanished, every rule below would vacuously pass.
      expect(rules.selectors.has('.os-herdr-status-dot')).toBe(true)
      expect(rules.selectors.has('.os-herdr-status-dot--waiting')).toBe(true)
      expect(rules.selectors.has('.os-herdr-status-dot--finished')).toBe(true)
    })

    it('resolves the waiting hue from a theme token, not a raw hex', () => {
      const decls = rules.bySelector.get('.os-herdr-status-dot--waiting') ?? []
      const background = decls.find((d) => d.prop === 'background-color')
      expect(background).toBeDefined()
      // A raw hex would be a theme violation (AGENTS.md §3) and would not
      // follow a theme switch.
      expect(background?.value.trim()).toMatch(/^var\(--color-[a-z0-9-]+\)$/)
    })

    it('gives each state its own colour source', () => {
      const waiting = rules.bySelector.get('.os-herdr-status-dot--waiting') ?? []
      const finished = rules.bySelector.get('.os-herdr-status-dot--finished') ?? []
      const hue = (list: Decl[]) =>
        list.find((d) => d.prop === 'background-color')?.value
      expect(hue(waiting)).toBeTruthy()
      expect(hue(finished)).toBeTruthy()
      // A shared hue would collapse "needs you" and "there is news" into one
      // undifferentiated state.
      expect(hue(waiting)).not.toBe(hue(finished))
    })

    it('drops the pulse under prefers-reduced-motion', () => {
      const reduced = rules.insideMedia('prefers-reduced-motion')
      const selectors = [...reduced.keys()].join(' ')
      expect(selectors).toContain('.os-herdr-status-dot--waiting')
      const decls = reduced.get('.os-herdr-status-dot--waiting') ?? []
      const animation = decls.find((d) => d.prop === 'animation')
      expect(animation).toBeDefined()
      // `none !important` — a later, weaker rule must not be able to revive
      // the pulse for a user who asked for less motion.
      expect(animation?.value.trim()).toBe('none')
      expect(animation?.important).toBe(true)
    })

    it('never hardcodes a colour in the dot rules', () => {
      for (const decls of rules.bySelector.values()) {
        for (const decl of decls) {
          if (!/^(background|background-color|color|border-color|fill)$/.test(decl.prop)) {
            continue
          }
          expect(decl.value).not.toMatch(/#[0-9a-f]{3,8}\b/i)
          expect(decl.value).not.toMatch(/\brgba?\(/i)
        }
      }
    })

    it('animates only the waiting state', () => {
      // Finished is news, not urgency: a pulse there would cry wolf every
      // time a turn ends.
      const finished = rules.bySelector.get('.os-herdr-status-dot--finished') ?? []
      expect(finished.some((d) => d.prop === 'animation')).toBe(false)
    })
  })

  describe('copy', () => {
    it('names each state in words', () => {
      expect(herdrStatusCopy('waiting', 'grok').text).toMatch(/waiting/i)
      expect(herdrStatusCopy('finished', 'grok').text).toMatch(/finished/i)
      expect(herdrStatusCopy('working', 'grok').text).toMatch(/working/i)
      expect(herdrStatusCopy('unknown', 'grok').text).toMatch(/unknown/i)
    })

    it('keeps the tone usable as a style hook', () => {
      expect(herdrStatusCopy('waiting', 'grok').tone).toBe('waiting')
      expect(herdrStatusCopy('finished', 'grok').tone).toBe('finished')
    })
  })

  describe('clearing on open', () => {
    it('clears the status and the unread mark when the chat is opened', () => {
      applyHerdrStatusFrame(frame({ status: 'done', mark_unread: true }))
      expect(isAgentUnread('herdr:w3:p1')).toBe(true)
      render(<ClearProbe seatId="herdr:w3:p1" open />)
      expect(isAgentUnread('herdr:w3:p1')).toBe(false)
    })

    it('does not clear when the chat is not open', () => {
      applyHerdrStatusFrame(frame({ status: 'done', mark_unread: true }))
      render(<ClearProbe seatId="herdr:w3:p1" open={false} />)
      expect(isAgentUnread('herdr:w3:p1')).toBe(true)
    })

    it('does not clear a different seat', () => {
      applyHerdrStatusFrame(frame({ status: 'done', mark_unread: true }))
      render(<ClearProbe seatId="herdr:other" open />)
      expect(isAgentUnread('herdr:w3:p1')).toBe(true)
    })

    it('a no-op clear does not resurrect a read seat', () => {
      markAgentRead('herdr:w3:p1')
      render(<ClearProbe seatId="herdr:w3:p1" open />)
      expect(isAgentUnread('herdr:w3:p1')).toBe(false)
      expect(screen.getByTestId('probe')).toBeInTheDocument()
    })
  })
})
