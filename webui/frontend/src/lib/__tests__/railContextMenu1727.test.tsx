/**
 * #1727 — the rail menu must not offer a click that cannot happen.
 *
 * A menu item rendered for a seat kind whose handler does nothing is a
 * silent no-op, and one whose handler does the WRONG thing is worse: before
 * this, a herdr row offered "Duplicate", `duplicateMenuRow` fell through to
 * the API branch and minted a custom API blueprint from a seat that has no
 * blueprint — a different kind of agent, created by a click that looked
 * harmless. `resolveMenuKind`'s own comment said herdr gets "no
 * Edit/Duplicate (no swarm-owned profile)"; nothing enforced it.
 *
 * Driven off `railMenuItems` (the real menu spec every surface renders) and
 * `RailMenuItem` (the real DOM), asserting on disabled state and the
 * accessible reason — never on the label alone.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { RAIL_MENU_REASONS, railMenuCapability, railMenuItems } from '../railContextMenu'
import RailContextMenu from '../../components/RailContextMenu'
import type { RailMenuItemId, RailMenuItemSpec } from '../railContextMenu'

const base = {
  pinned: false,
  hidden: false,
  unread: false,
} as const

function menuFor(kind: Parameters<typeof railMenuItems>[0]['kind'], extra = {}) {
  return railMenuItems({ ...base, kind, ...extra })
}

function specFor(items: RailMenuItemSpec[], id: RailMenuItemId) {
  return items.find((item) => item.id === id)
}

afterEach(cleanup)

describe('#1727 the capability matrix has one answer per kind and item', () => {
  it('api seats can do everything they are offered', () => {
    for (const id of ['edit', 'duplicate', 'new-session', 'select-session'] as const) {
      expect(railMenuCapability('api', id)).toEqual({ supported: true })
    }
  })

  it('herdr seats cannot edit a profile or be duplicated', () => {
    expect(railMenuCapability('herdr', 'edit')).toEqual({
      supported: false,
      reason: RAIL_MENU_REASONS.herdrNoProfile,
    })
    expect(railMenuCapability('herdr', 'duplicate')).toEqual({
      supported: false,
      reason: RAIL_MENU_REASONS.herdrNoDuplicate,
    })
  })

  it('a chat row is a session: no profile of its own, nothing to duplicate', () => {
    expect(railMenuCapability('chat', 'edit').supported).toBe(false)
    expect(railMenuCapability('chat', 'duplicate').supported).toBe(false)
    // …and a chat row is still the one kind that always knows its
    // conversation id, so Copy must not be greying out on it.
    expect(railMenuCapability('chat', 'copy-id')).toEqual({ supported: true })
  })

  it('kinds whose conversations live in the provider have no swarm sessions', () => {
    for (const kind of ['team', 'remote', 'herdr'] as const) {
      expect(railMenuCapability(kind, 'new-session')).toMatchObject({
        supported: false,
        reason: RAIL_MENU_REASONS.noSwarmSessions,
      })
      expect(railMenuCapability(kind, 'select-session')).toMatchObject({ supported: false })
    }
  })

  it('cli keeps the pre-existing honest OMIT for Edit and Duplicate', () => {
    // REQ-82 predates #1727 and is asserted elsewhere; the matrix must not
    // quietly turn it into a grey row, and must not lose the reason.
    for (const id of ['edit', 'duplicate'] as const) {
      expect(railMenuCapability('cli', id)).toMatchObject({ supported: false, omit: true })
    }
  })
})

describe('#1727 the spec carries the grey and the reason', () => {
  it('greys Edit and Duplicate for a herdr row instead of offering them', () => {
    const items = menuFor('herdr')
    const edit = specFor(items, 'edit')
    const duplicate = specFor(items, 'duplicate')
    expect(edit).toMatchObject({
      id: 'edit',
      label: 'Edit Profile',
      disabled: true,
      reason: RAIL_MENU_REASONS.herdrNoProfile,
    })
    expect(duplicate).toMatchObject({
      id: 'duplicate',
      disabled: true,
      reason: RAIL_MENU_REASONS.herdrNoDuplicate,
    })
    // The honest capability is now visible in the menu, not hidden.
    expect(items.map((item) => item.id)).toContain('edit')
  })

  it('leaves the same items enabled for the kinds that can do them', () => {
    for (const kind of ['api', 'blueprint', 'team', 'remote'] as const) {
      expect(specFor(menuFor(kind), 'edit')).toMatchObject({ disabled: undefined })
      expect(specFor(menuFor(kind), 'duplicate')).toMatchObject({ disabled: undefined })
    }
  })

  it('greys New session when a caller asks for it on a kind that has none', () => {
    // The rail currently omits the item for these kinds, so this is the
    // contract for any caller that DOES offer it: grey with the reason, never
    // a click that quietly does nothing.
    const items = menuFor('remote', { hasNewSession: true, hasSelectSession: true })
    expect(specFor(items, 'new-session')).toMatchObject({
      label: 'New session',
      disabled: true,
      reason: RAIL_MENU_REASONS.noSwarmSessions,
    })
    expect(specFor(items, 'select-session')).toMatchObject({ disabled: true })
  })

  it('does not grey New session for the kinds that own swarm-side sessions', () => {
    for (const kind of ['api', 'blueprint'] as const) {
      expect(specFor(menuFor(kind, { hasNewSession: true }), 'new-session')).toMatchObject({
        disabled: undefined,
        reason: undefined,
      })
    }
  })
})

describe('#1727 the rendered menu really is disabled and explains itself', () => {
  const items: RailMenuItemSpec[] = menuFor('herdr')

  it('renders the greyed items as disabled menu items carrying the reason', () => {
    render(
      <RailContextMenu
        agentName="Herdr seat"
        x={0}
        y={0}
        items={items}
        onSelect={() => undefined}
      />,
    )
    const edit = screen.getByRole('menuitem', { name: /Edit Profile/ })
    const duplicate = screen.getByRole('menuitem', { name: /Duplicate/ })
    expect(edit).toBeDisabled()
    expect(edit).toHaveAttribute('title', RAIL_MENU_REASONS.herdrNoProfile)
    expect(duplicate).toBeDisabled()
    expect(duplicate).toHaveAttribute('title', RAIL_MENU_REASONS.herdrNoDuplicate)
    // A greyed item is not merely styled that way — it is unfocusable and
    // unclickable, which is what stops the silent no-op.
    expect(edit).toHaveAttribute('aria-disabled', 'true')
  })

  it('an enabled item on the same menu is still live', () => {
    const onSelect = vi.fn()
    render(
      <RailContextMenu agentName="Herdr seat" x={0} y={0} items={items} onSelect={onSelect} />,
    )
    const hide = screen.getByRole('menuitem', { name: /Hide from sidebar/ })
    expect(hide).not.toBeDisabled()
    hide.click()
    expect(onSelect).toHaveBeenCalledWith('hide')
  })

  it('clicking a greyed item dispatches nothing at all', () => {
    const onSelect = vi.fn()
    render(
      <RailContextMenu agentName="Herdr seat" x={0} y={0} items={items} onSelect={onSelect} />,
    )
    screen.getByRole('menuitem', { name: /Duplicate/ }).click()
    expect(onSelect).not.toHaveBeenCalled()
  })
})
