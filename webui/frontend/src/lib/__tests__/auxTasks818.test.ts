/**
 * #818 — the aux-task reducer contract.
 *
 * `aux_task_started` inserts a running row; `aux_task_update` finishes it and
 * keeps it in a 4s decay window; unknown frame types are ignored; kill-switch
 * requests ride `swarm:aux-cancel`.
 */
import { describe, expect, it } from 'vitest'
import {
  applyAuxFrame,
  activeAuxTasks,
  sweepAuxTasks,
  requestAuxCancel,
  AUX_CANCEL_EVENT,
} from '../auxTasks'

const started = (id: string, label = 'Advisor note') =>
  applyAuxFrame([], { type: 'aux_task_started', task_id: id, label, model: 'gpt-4o-mini' })

describe('#818 aux task reducer', () => {
  it('inserts a running row on aux_task_started', () => {
    const tasks = started('aux-1')
    expect(tasks).toHaveLength(1)
    expect(tasks[0]).toMatchObject({ task_id: 'aux-1', state: 'running', label: 'Advisor note' })
  })

  it('a finish moves the row into the decay window', () => {
    let tasks = started('aux-1')
    tasks = applyAuxFrame(tasks, { type: 'aux_task_update', task_id: 'aux-1', state: 'done', duration_s: 1.4 })
    expect(tasks[0].state).toBe('done')
    expect(activeAuxTasks(tasks)).toHaveLength(0)
  })

  it('decayed rows sweep away', () => {
    let tasks = started('aux-1')
    tasks = applyAuxFrame(tasks, { type: 'aux_task_update', task_id: 'aux-1', state: 'done', duration_s: 0.2 })
    const afterDecay = Date.now() + 5_000
    expect(sweepAuxTasks(tasks, afterDecay)).toHaveLength(0)
    // Still present inside the window.
    expect(sweepAuxTasks(tasks)).toHaveLength(1)
  })

  it('unknown frame types are ignored', () => {
    expect(applyAuxFrame([], { type: 'chat_message', task_id: 'x' } as never)).toHaveLength(0)
  })

  it('frames without an id are ignored', () => {
    expect(applyAuxFrame([], { type: 'aux_task_started', task_id: '' })).toHaveLength(0)
  })

  it('cancel requests dispatch the kill event', () => {
    const seen: string[] = []
    const handler = (e: Event) => seen.push((e as CustomEvent).detail)
    window.addEventListener(AUX_CANCEL_EVENT, handler)
    requestAuxCancel('aux-9')
    window.removeEventListener(AUX_CANCEL_EVENT, handler)
    expect(seen).toEqual(['aux-9'])
  })
})
