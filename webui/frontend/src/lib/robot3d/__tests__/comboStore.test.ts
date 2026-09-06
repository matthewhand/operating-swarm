import { afterEach, describe, expect, it } from 'vitest'
import { defaultCombo } from '../catalog'
import {
  ROBOT3D_COMBO_SET_EVENT,
  ROBOT3D_COMBO_STORAGE_KEY,
  loadRobot3dCombo,
  saveRobot3dCombo,
} from '../comboStore'

describe('robot3d combo store', () => {
  afterEach(() => {
    localStorage.removeItem(ROBOT3D_COMBO_STORAGE_KEY)
  })

  it('defaults to the first legal combo when unset', () => {
    expect(loadRobot3dCombo()).toEqual(defaultCombo())
  })

  it('persists a legal combo and reloads it', () => {
    const combo = { bodyId: 'column', headId: 'dish_visor' }
    saveRobot3dCombo(combo)
    expect(localStorage.getItem(ROBOT3D_COMBO_STORAGE_KEY)).toContain('dish_visor')
    expect(loadRobot3dCombo()).toEqual(combo)
  })

  it('falls back to the default on unknown ids and malformed JSON', () => {
    localStorage.setItem(ROBOT3D_COMBO_STORAGE_KEY, JSON.stringify({ bodyId: 'nope', headId: 'x' }))
    expect(loadRobot3dCombo()).toEqual(defaultCombo())
    localStorage.setItem(ROBOT3D_COMBO_STORAGE_KEY, '{broken')
    expect(loadRobot3dCombo()).toEqual(defaultCombo())
  })

  it('dispatches a same-tab event on save', () => {
    const seen: unknown[] = []
    const onSet = (event: Event) => seen.push((event as CustomEvent).detail)
    window.addEventListener(ROBOT3D_COMBO_SET_EVENT, onSet)
    saveRobot3dCombo({ bodyId: 'column', headId: 'mini_dome' })
    window.removeEventListener(ROBOT3D_COMBO_SET_EVENT, onSet)
    expect(seen).toHaveLength(1)
  })
})