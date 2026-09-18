/**
 * #634 — the palette (the single routing surface after #504) carries the full
 * keyboard contract: ↑↓/Home/End within rows, inline-end (→ in LTR) descends
 * from an agent row into its model group, inline-start (←) returns or reaches
 * the scope row, and the scope row itself participates in navigation.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ModelSearchPalette, { type ModelSearchOption } from '../ModelSearchPalette'

const ROWS: ModelSearchOption[] = [
  { id: 'agy', label: 'agy', description: 'Agent', provider: 'CLI', kind: 'cli' },
  { id: 'grok', label: 'grok', description: 'Agent', provider: 'CLI', kind: 'cli' },
  { id: 'm1', label: 'Model One', description: 'Model', provider: 'CLI · agy models', tag: 'model' },
  { id: 'm2', label: 'Model Two', description: 'Model', provider: 'CLI · agy models', tag: 'model' },
]

const ALL: ModelSearchOption[] = [
  ...ROWS,
  { id: 'api_agent', label: 'API Agent', description: 'Agent', provider: 'All agents', kind: 'api' },
]

function renderPalette(
  props: Partial<Parameters<typeof ModelSearchPalette>[0]> = {},
) {
  const onSelect = vi.fn()
  const onClearScope = vi.fn()
  render(
    <ModelSearchPalette
      open
      models={ROWS}
      allModels={ALL}
      scopeLabel="CLI · agy models"
      selectedId="m1"
      onClose={vi.fn()}
      onSelect={onSelect}
      onClearScope={onClearScope}
      {...props}
    />,
  )
  return { onSelect, onClearScope }
}

function activeRow() {
  return document.querySelector<HTMLElement>('.os-search-row--active')
}

afterEach(() => {
  document.documentElement.removeAttribute('dir')
})

describe('ModelSearchPalette keyboard contract (#634)', () => {
  it('ArrowRight descends from an agent row into its model group; ArrowLeft returns', () => {
    renderPalette()
    expect(activeRow()).toHaveAttribute('data-model-id', 'agy')
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(activeRow()).toHaveAttribute('data-model-id', 'm1')
    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(activeRow()).toHaveAttribute('data-model-id', 'agy')
  })

  it('ArrowUp from the very top focuses the scope row; Enter on the chip clears scope', () => {
    const { onClearScope } = renderPalette()
    fireEvent.keyDown(window, { key: 'ArrowUp' })
    expect(screen.getByTestId('os-palette-scope-row')).toHaveClass(
      'os-search-palette__scope--focus',
    )
    fireEvent.keyDown(screen.getByTestId('os-palette-scope'), { key: 'Enter' })
    expect(onClearScope).toHaveBeenCalledTimes(1)
    // Scope cleared → the full catalog (incl. other kinds) is visible.
    expect(screen.getByTestId('os-model-row-api_agent')).toBeInTheDocument()
  })

  it('Home/End jump to the first/last visible row', () => {
    renderPalette()
    fireEvent.keyDown(window, { key: 'End' })
    expect(activeRow()).toHaveAttribute('data-model-id', 'm2')
    fireEvent.keyDown(window, { key: 'Home' })
    expect(activeRow()).toHaveAttribute('data-model-id', 'agy')
  })

  it('RTL mirrors the inline direction: ← descends, → returns', () => {
    document.documentElement.setAttribute('dir', 'rtl')
    renderPalette()
    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(activeRow()).toHaveAttribute('data-model-id', 'm1')
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(activeRow()).toHaveAttribute('data-model-id', 'agy')
  })

  it('the reveal control toggles the scope back on ("Showing all — restore scope")', () => {
    renderPalette()
    const clear = screen.getByTestId('os-palette-scope-clear')
    fireEvent.click(clear)
    expect(screen.getByTestId('os-model-row-api_agent')).toBeInTheDocument()
    fireEvent.click(clear)
    expect(screen.queryByTestId('os-model-row-api_agent')).not.toBeInTheDocument()
  })
})
