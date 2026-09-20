import { afterEach, describe, expect, it } from 'vitest'
import {
  GENERATION_COMPLETE_EVENT,
  RAIL_ORDER_STORAGE_KEY,
  applyRailOrder,
  bumpRailIdToTop,
  generationCompleteDetail,
  insertRailIdAfter,
  loadRailOrder,
  mergeRailOrder,
  moveRailId,
  notifyGenerationComplete,
  saveRailOrder,
} from '../railOrder'

describe('railOrder persistence', () => {
  afterEach(() => {
    localStorage.removeItem(RAIL_ORDER_STORAGE_KEY)
  })

  it('starts empty, persists a drag order, and reloads it', () => {
    expect(loadRailOrder()).toEqual([])
    expect(saveRailOrder(['stewie', 'support', 'codey'])).toEqual([
      'stewie',
      'support',
      'codey',
    ])
    expect(JSON.parse(localStorage.getItem(RAIL_ORDER_STORAGE_KEY) || '[]')).toEqual([
      'stewie',
      'support',
      'codey',
    ])
    expect(loadRailOrder()).toEqual(['stewie', 'support', 'codey'])
  })

  it('ignores corrupt storage and empty ids', () => {
    localStorage.setItem(RAIL_ORDER_STORAGE_KEY, '{not-json')
    expect(loadRailOrder()).toEqual([])
    localStorage.setItem(RAIL_ORDER_STORAGE_KEY, JSON.stringify([1, '', 'ok', 'ok']))
    expect(loadRailOrder()).toEqual(['ok'])
  })

  it('applies stored order and appends new catalog rows', () => {
    const items = [{ id: 'support' }, { id: 'codey' }, { id: 'stewie' }]
    expect(applyRailOrder(items, ['stewie', 'codey']).map((item) => item.id)).toEqual([
      'stewie',
      'codey',
      'support',
    ])
  })

  it('moves a row before another and bumps a completed id to index 0', () => {
    const start = ['support', 'codey', 'stewie']
    expect(moveRailId(start, 'stewie', 'support')).toEqual(['stewie', 'support', 'codey'])
    expect(moveRailId(start, 'codey', 'codey')).toEqual(start)
    expect(bumpRailIdToTop(start, 'stewie')).toEqual(['stewie', 'support', 'codey'])
    expect(mergeRailOrder(['stewie'], ['support', 'codey', 'stewie'])).toEqual([
      'stewie',
      'support',
      'codey',
    ])
  })

  it('REQ-128: maintains stable relative order among ties and allows manual reorder override', () => {
    const start = ['alpha', 'beta', 'gamma', 'delta']
    // Gamma completes -> moves to index 0
    const afterGamma = bumpRailIdToTop(start, 'gamma')
    expect(afterGamma).toEqual(['gamma', 'alpha', 'beta', 'delta'])

    // Beta completes next -> moves to index 0, gamma stays in front of alpha/delta
    const afterBeta = bumpRailIdToTop(afterGamma, 'beta')
    expect(afterBeta).toEqual(['beta', 'gamma', 'alpha', 'delta'])

    // Re-bumping beta is idempotent
    expect(bumpRailIdToTop(afterBeta, 'beta')).toEqual(afterBeta)

    // Empty or missing ID leaves order untouched
    expect(bumpRailIdToTop(afterBeta, '')).toEqual(afterBeta)

    // Manual drag reordering overrides rail order until next completion
    const reordered = moveRailId(afterBeta, 'delta', 'beta')
    expect(reordered).toEqual(['delta', 'beta', 'gamma', 'alpha'])

    // Subsequent generation completion moves the completed agent back to index 0
    const afterAlpha = bumpRailIdToTop(reordered, 'alpha')
    expect(afterAlpha).toEqual(['alpha', 'delta', 'beta', 'gamma'])
  })

  it('notifies generation complete with optional snippet and failed flag', () => {
    const seen: unknown[] = []
    const onComplete = (event: Event) => {
      seen.push(generationCompleteDetail(event))
    }
    window.addEventListener(GENERATION_COMPLETE_EVENT, onComplete)
    notifyGenerationComplete('')
    notifyGenerationComplete('codey', { snippet: 'done', agentName: 'Codey', failed: true })
    window.removeEventListener(GENERATION_COMPLETE_EVENT, onComplete)
    expect(seen).toEqual([
      { agentId: 'codey', snippet: 'done', agentName: 'Codey', failed: true },
    ])
  })

  it('inserts newId immediately after afterId without moving existing items to top', () => {
    const start = ['support', 'remote:trueforge', 'codey']
    expect(insertRailIdAfter(start, 'remote:trueforge_copy', 'remote:trueforge')).toEqual([
      'support',
      'remote:trueforge',
      'remote:trueforge_copy',
      'codey',
    ])
    // If afterId is absent or missing, insert at start
    expect(insertRailIdAfter(start, 'other', 'nonexistent')).toEqual([
      'other',
      'support',
      'remote:trueforge',
      'codey',
    ])
    // Re-inserting existing item moves it immediately after target
    expect(insertRailIdAfter(start, 'codey', 'support')).toEqual([
      'support',
      'codey',
      'remote:trueforge',
    ])
  })
})
