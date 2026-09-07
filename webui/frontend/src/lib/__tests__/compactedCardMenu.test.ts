import { describe, expect, it } from 'vitest'
import {
  COMPACTED_CARD_COPY_EMPTY,
  COMPACTED_CARD_DELETE_HONESTY,
  compactedCardCopyText,
  compactedCardMenuItems,
  messageFromLabel,
} from '../compactedCardMenu'

describe('compactedCardMenuItems (REQ-213)', () => {
  it('toggles Expand/Collapse and puts danger Remove from view last', () => {
    const collapsed = compactedCardMenuItems({ expanded: false })
    expect(collapsed.map((item) => item.id)).toEqual(['expand', 'copy', 'delete'])
    expect(collapsed[0]).toMatchObject({ id: 'expand', label: 'Expand' })

    const expanded = compactedCardMenuItems({ expanded: true })
    expect(expanded.map((item) => item.id)).toEqual(['collapse', 'copy', 'delete'])
    expect(expanded.at(-1)).toMatchObject({
      id: 'delete',
      label: 'Remove from view',
      danger: true,
      reason: COMPACTED_CARD_DELETE_HONESTY,
    })
    expect(COMPACTED_CARD_DELETE_HONESTY).toMatch(/view only/i)
    expect(COMPACTED_CARD_DELETE_HONESTY).toMatch(/disk/i)
  })

  it('disables Copy when there is no underlying text', () => {
    const items = compactedCardMenuItems({ expanded: false, canCopy: false })
    expect(items.find((item) => item.id === 'copy')).toMatchObject({
      disabled: true,
      reason: COMPACTED_CARD_COPY_EMPTY,
    })
  })

  it('labels System vs agent sources the same family', () => {
    expect(messageFromLabel('System')).toBe('Message from System')
    expect(messageFromLabel('Codey')).toBe('Message from Codey')
  })

  it('copies summary plus original compacted turns as underlying text', () => {
    expect(compactedCardCopyText({ text: 'digest' })).toBe('digest')
    expect(
      compactedCardCopyText({
        text: 'digest',
        compacted: [
          { role: 'user', text: 'Ship it' },
          { role: 'assistant', agent: 'Codey', text: 'Done' },
        ],
      }),
    ).toBe('digest\n\n---\n[user]: Ship it\n\n[Codey]: Done')
  })
})
  it('omits empty lines and separator when all compacted items are empty', () => {
    expect(
      compactedCardCopyText({
        text: 'main digest',
        compacted: [{ role: 'user', text: '' }, { role: 'assistant', text: '   ' }],
      }),
    ).toBe('main digest')
  })

