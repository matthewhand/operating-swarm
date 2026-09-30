import { describe, expect, it } from 'vitest'
import { RIG, RIGS, RIG_EDGE_LABEL, rigWord } from '../rigLabels'

describe('#1222 / #1362 group chat display vocabulary', () => {
  it('exposes singular/plural terms for operator copy', () => {
    expect(RIG).toBe('Group chat')
    expect(RIGS).toBe('Group chats')
    expect(rigWord(1)).toBe('Group chat')
    expect(rigWord(2)).toBe('Group chats')
    expect(rigWord(1, { lower: true })).toBe('group chat')
    expect(rigWord(0, { lower: true })).toBe('group chats')
  })

  it('names the OpenRig edge kinds 1:1', () => {
    expect(RIG_EDGE_LABEL.delegates_to).toBe('delegates to')
    expect(RIG_EDGE_LABEL.collaborates_with).toBe('collaborates with')
    expect(RIG_EDGE_LABEL.can_observe).toBe('can observe')
  })
})
