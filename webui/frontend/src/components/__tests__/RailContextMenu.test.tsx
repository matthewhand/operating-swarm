import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import RailContextMenu from '../RailContextMenu'
import { railMenuItems } from '../../lib/railContextMenu'

describe('RailContextMenu (REQ-82)', () => {
  it('renders an icon on every item and styles Delete last as danger/red', () => {
    const items = railMenuItems({
      kind: 'api',
      pinned: true,
      hidden: false,
      unread: false,
    })
    const onSelect = vi.fn()
    render(
      <RailContextMenu agentName="Codey" x={12} y={24} items={items} onSelect={onSelect} />,
    )

    const menu = screen.getByRole('menu', { name: 'Actions for Codey' })
    expect(menu).toHaveClass('menu')
    const menuitems = within(menu).getAllByRole('menuitem')
    expect(menuitems.map((el) => el.textContent)).toEqual([
      'Unpin',
      'Move to',
      'Mark as unread',
      'Edit Profile',
      'Duplicate',
      'Copy conversation ID',
      'Hide from sidebar',
      'Notifications: Off',
      'Delete',
    ])
    for (const item of menuitems) {
      expect(item.querySelector('[data-menu-icon]')).toBeTruthy()
    }
    const del = menuitems.at(-1)!
    expect(del).toHaveClass('text-error')
    expect(del.querySelector('[data-menu-icon="delete"]')).toHaveClass('text-error')
    fireEvent.click(del)
    expect(onSelect).toHaveBeenCalledWith('delete')
  })

  it('clamps into the viewport instead of clipping at the bottom edge', () => {
    const items = railMenuItems({
      kind: 'api',
      pinned: false,
      hidden: false,
      unread: false,
    })
    render(
      <RailContextMenu agentName="Codey" x={2000} y={2000} items={items} onSelect={vi.fn()} />,
    )
    const menu = screen.getByRole('menu', { name: 'Actions for Codey' })
    expect(Number.parseFloat(menu.style.top)).toBeLessThan(2000)
    expect(Number.parseFloat(menu.style.left)).toBeLessThan(2000)
  })

  it('omits Edit Profile and Duplicate on CLI menus', () => {
    const items = railMenuItems({
      kind: 'cli',
      pinned: false,
      hidden: false,
      unread: false,
      canCopyId: false,
    })
    render(
      <RailContextMenu agentName="cli_agent" x={0} y={0} items={items} onSelect={() => undefined} />,
    )
    expect(screen.queryByRole('menuitem', { name: /Edit Profile/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /Duplicate/i })).not.toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /Copy conversation ID/i })).toBeDisabled()
    const terminate = screen.getByRole('menuitem', { name: /^Terminate$/i })
    expect(terminate).toBeDisabled()
    expect(terminate).toHaveAttribute('title', 'Nothing running')
    expect(terminate.querySelector('[data-menu-icon="terminate"]')).toBeTruthy()
    expect(terminate).not.toHaveClass('text-error')
    const menuitems = screen.getAllByRole('menuitem')
    expect(menuitems.at(-1)).toHaveTextContent('Delete')
    expect(menuitems.at(-1)).toHaveClass('text-error')
  })
})
