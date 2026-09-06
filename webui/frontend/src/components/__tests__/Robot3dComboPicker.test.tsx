import { afterEach, describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import Robot3dComboPicker from '../Robot3dComboPicker'
import { ROBOT3D_COMBO_STORAGE_KEY } from '../../lib/robot3d/comboStore'
import { defaultCombo } from '../../lib/robot3d/catalog'

describe('Robot3dComboPicker (REQ-194 Phase 2)', () => {
  afterEach(() => {
    localStorage.removeItem(ROBOT3D_COMBO_STORAGE_KEY)
  })

  it('lists the body and head catalogs with the default combo selected', () => {
    render(<Robot3dComboPicker />)
    expect(screen.getByTestId('robot3d-combo-picker')).toBeInTheDocument()
    const body = screen.getByLabelText('Body')
    const head = screen.getByLabelText('Head')
    expect(body).toHaveValue(defaultCombo().bodyId)
    expect(head).toHaveValue(defaultCombo().headId)
    // >= 2 bodies x >= 2 heads options
    expect(within(body).getAllByRole('option').length).toBeGreaterThanOrEqual(2)
    expect(within(head).getAllByRole('option').length).toBeGreaterThanOrEqual(2)
  })

  it('persists a changed combo to the sub-key', () => {
    render(<Robot3dComboPicker />)
    fireEvent.change(screen.getByLabelText('Head'), { target: { value: 'dish_visor' } })
    const stored = JSON.parse(
      localStorage.getItem(ROBOT3D_COMBO_STORAGE_KEY) ?? '{}',
    ) as { headId?: string }
    expect(stored.headId).toBe('dish_visor')
  })
})