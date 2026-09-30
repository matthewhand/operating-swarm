/**
 * #1729 — the Herdr status surface as the rail actually renders it.
 *
 * The dot is mounted by `RailRowSlot`, the row's existing name-line slot, so
 * these tests assert the whole path: a Herdr seat row carrying a status lights
 * the indicator, a non-Herdr row never does, and the existing unread dot and
 * role badge keep their precedence.
 *
 * The rail renderers themselves (`rowsRender`, `AgentSidebar`) are owned
 * elsewhere, so the slot resolves its own seat id from the row's
 * `data-agent-id` — which is exactly what these tests verify works.
 */

import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import RailRowSlot from '../RailRowSlot'
import {
  applyHerdrStatusFrame,
  resetHerdrStatusStore,
  type HerdrStatusFrame,
} from '../../lib/herdrStatus'
import { markAgentUnread } from '../../lib/unreadAgents'

function frame(over: Partial<HerdrStatusFrame> = {}): HerdrStatusFrame {
  return {
    type: 'herdr_status',
    seat_id: 'herdr:w3:p1',
    target: 'w3:p1',
    status: 'blocked',
    ...over,
  }
}

/** A row wrapper, matching what the rail renders around the slot. */
function Row({
  agentId,
  children,
}: {
  agentId: string
  children: React.ReactNode
}) {
  return (
    <a href="/chat" data-agent-id={agentId}>
      {children}
    </a>
  )
}

describe('#1729 rail row status surface', () => {
  beforeEach(() => {
    localStorage.clear()
    resetHerdrStatusStore()
  })
  afterEach(cleanup)

  it('shows the indicator when the Herdr seat is waiting on a question', () => {
    applyHerdrStatusFrame(frame({ status: 'blocked' }))
    render(
      <Row agentId="herdr:w3:p1">
        <RailRowSlot seatId="herdr:w3:p1" dataLabel="grok" />
      </Row>,
    )
    expect(screen.getByTestId('herdr-status-dot')).toBeInTheDocument()
    expect(screen.getByRole('status').getAttribute('aria-label')).toBe(
      'grok: waiting on you',
    )
  })

  it('resolves its own seat id from the row it sits in', () => {
    // The rail renderers are owned elsewhere, so the slot must identify its
    // seat without a prop threaded through them.
    applyHerdrStatusFrame(frame({ status: 'blocked' }))
    render(
      <Row agentId="herdr:w3:p1">
        <RailRowSlot dataLabel="grok" />
      </Row>,
    )
    expect(screen.getByTestId('herdr-status-dot')).toBeInTheDocument()
  })

  it('does not light for a non-Herdr seat', () => {
    applyHerdrStatusFrame(frame({ status: 'blocked' }))
    render(
      <Row agentId="grok">
        <RailRowSlot dataLabel="grok" />
      </Row>,
    )
    // A stale status reading must never bleed onto an unrelated seat.
    expect(screen.queryByTestId('herdr-status-dot')).toBeNull()
  })

  it('does not light for a working seat — the rail already shows busy', () => {
    applyHerdrStatusFrame(frame({ status: 'working' }))
    render(
      <Row agentId="herdr:w3:p1">
        <RailRowSlot dataLabel="grok" />
      </Row>,
    )
    expect(screen.queryByTestId('herdr-status-dot')).toBeNull()
  })

  it('waiting outranks the unread dot — a question is more urgent', () => {
    applyHerdrStatusFrame(frame({ status: 'blocked' }))
    markAgentUnread('herdr:w3:p1')
    render(
      <Row agentId="herdr:w3:p1">
        <RailRowSlot seatId="herdr:w3:p1" unread dataLabel="grok" />
      </Row>,
    )
    // The badge would otherwise hide the very state the unread is about.
    expect(screen.getByTestId('herdr-status-dot')).toBeInTheDocument()
    expect(screen.getByTestId('rail-unread-dot')).toBeInTheDocument()
  })

  it('keeps the existing unread dot and role badge behaviour intact', () => {
    render(
      <Row agentId="herdr:w3:p1">
        <RailRowSlot
          seatId="herdr:w3:p1"
          unread
          dataRole="dev"
          badge={<span data-testid="role-badge">DEV</span>}
          timestampLabel="2m"
        />
      </Row>,
    )
    // Unread still wins the slot, and the badge still yields to it (#501).
    expect(screen.getByTestId('rail-unread-dot')).toBeInTheDocument()
    expect(screen.queryByTestId('rail-row-timestamp')).toBeNull()
    expect(screen.queryByTestId('role-badge')).toBeNull()
  })

  it('still shows the timestamp when there is nothing to say', () => {
    render(
      <Row agentId="herdr:w3:p1">
        <RailRowSlot seatId="herdr:w3:p1" timestampLabel="2m" />
      </Row>,
    )
    expect(screen.getByTestId('rail-row-timestamp')).toHaveTextContent('2m')
  })

  it('publishes the seat status on the slot for other chrome to read', () => {
    applyHerdrStatusFrame(frame({ status: 'blocked' }))
    render(
      <Row agentId="herdr:w3:p1">
        <RailRowSlot seatId="herdr:w3:p1" />
      </Row>,
    )
    expect(screen.getByTestId('rail-row-slot').getAttribute('data-herdr-status')).toBe(
      'waiting',
    )
  })

  it('a Herdr row with no status reports unknown, not idle', () => {
    render(
      <Row agentId="herdr:never-heard-of">
        <RailRowSlot />
      </Row>,
    )
    // "unknown" is the honest default; "idle" would claim Herdr said so.
    expect(screen.getByTestId('rail-row-slot').getAttribute('data-herdr-status')).toBe(
      'unknown',
    )
    expect(screen.queryByTestId('herdr-status-dot')).toBeNull()
  })

  it('a non-Herdr row carries no status attribute at all', () => {
    render(
      <Row agentId="grok">
        <RailRowSlot />
      </Row>,
    )
    expect(screen.getByTestId('rail-row-slot').getAttribute('data-herdr-status')).toBeNull()
  })

  it('re-renders when the seat status changes', () => {
    render(
      <Row agentId="herdr:w3:p1">
        <RailRowSlot seatId="herdr:w3:p1" dataLabel="grok" />
      </Row>,
    )
    expect(screen.queryByTestId('herdr-status-dot')).toBeNull()
    // The subscription must be live: a status arriving after mount has to
    // appear without a reload. `act` because the store change is external to
    // React — without it the assertion would race the commit.
    act(() => {
      applyHerdrStatusFrame(frame({ status: 'blocked' }))
    })
    expect(screen.getByTestId('herdr-status-dot')).toBeInTheDocument()
  })
})

// Deliberate non-regression guard — passes before and after the change.
describe('#1729 rail slot non-regression guard', () => {
  beforeEach(() => {
    localStorage.clear()
    resetHerdrStatusStore()
  })
  afterEach(cleanup)

  it('guard: a row with no Herdr props renders exactly as it did before', () => {
    const { container } = render(
      <Row agentId="grok">
        <RailRowSlot timestampLabel="5m" />
      </Row>,
    )
    const slot = container.querySelector('[data-testid="rail-row-slot"]')
    expect(slot?.getAttribute('data-herdr-status')).toBeNull()
    expect(container.querySelector('[data-testid="rail-row-timestamp"]')).not.toBeNull()
  })

  it('guard: the existing unread store still drives the rail dot', () => {
    // The Herdr path reuses this store. If its contract moved, every unread
    // affordance in the app moved with it. Passes both ways.
    markAgentUnread('some-seat')
    render(
      <Row agentId="some-seat">
        <RailRowSlot unread />
      </Row>,
    )
    expect(screen.getByTestId('rail-unread-dot')).toBeInTheDocument()
  })
})
