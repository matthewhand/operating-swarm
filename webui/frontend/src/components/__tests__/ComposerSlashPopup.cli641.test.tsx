/**
 * #641 — CLI-declared commands render in the slash popup as their own group;
 * an unavailable command is visibly disabled with the provider's reason and
 * cannot be selected.
 */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ComposerSlashPopup } from '../ComposerSlashPopup'
import { buildSlashCatalog, filterSlashItems, type SlashItem } from '../../lib/slashMenu'

function renderPopup(items: SlashItem[], onSelectItem: (item: SlashItem) => void) {
  return render(
    <ComposerSlashPopup
      open
      query=""
      items={items}
      selectedIndex={0}
      onSelectIndex={vi.fn()}
      onSelectItem={onSelectItem}
    />,
  )
}

const catalog = buildSlashCatalog(undefined, [
  {
    name: 'compress',
    description: 'Compact this omp session context',
    available: false,
    unavailable_reason: 'omp cannot compress in non-interactive (print) mode',
  },
])
const items = filterSlashItems(catalog, '', [])

describe('#641 ComposerSlashPopup CLI commands', () => {
  it('renders a CLI Commands group with the command', () => {
    renderPopup(items, vi.fn())
    expect(screen.getByText('CLI Commands')).toBeInTheDocument()
    expect(screen.getByTestId('slash-item-cli-compress')).toBeInTheDocument()
  })

  it('renders an unavailable command disabled with the reason', () => {
    renderPopup(items, vi.fn())
    const btn = screen.getByTestId('slash-item-cli-compress')
    expect(btn).toBeDisabled()
    expect(btn).toHaveAttribute('title', 'omp cannot compress in non-interactive (print) mode')
    expect(screen.getByText('Unavailable')).toBeInTheDocument()
  })

  it('never fires onSelectItem for an unavailable command', () => {
    const onSelectItem = vi.fn()
    renderPopup(items, onSelectItem)
    fireEvent.click(screen.getByTestId('slash-item-cli-compress'))
    expect(onSelectItem).not.toHaveBeenCalled()
  })

  it('keeps available CLI commands selectable with a CLI badge', () => {
    const ready = filterSlashItems(
      buildSlashCatalog(undefined, [
        { name: 'review', description: 'Run the CLI review', available: true },
      ]),
      '',
      [],
    )
    const onSelectItem = vi.fn()
    renderPopup(ready, onSelectItem)
    const btn = screen.getByTestId('slash-item-cli-review')
    expect(btn).toBeEnabled()
    fireEvent.click(btn)
    expect(onSelectItem).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'cli-review', kind: 'cli' }),
    )
  })
})
