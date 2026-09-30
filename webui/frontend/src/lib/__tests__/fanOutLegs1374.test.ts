/**
 * #1374 — fan-out leg reducer and the cancel frame for one id.
 */
import { describe, expect, it } from 'vitest'
import { buildCancelFanOutLegFrame, parseChatWsMessage } from '../chatWs'
import { applyFanOutLeg, cardsForFanOutLegs, type FanOutLeg } from '../runningCards'

describe('applyFanOutLeg', () => {
  it('streams queued → running → done for a stable id', () => {
    let legs: FanOutLeg[] = []
    legs = applyFanOutLeg(legs, {
      id: 'alpha',
      label: 'Alpha',
      status: 'queued',
      legKind: 'blueprint',
      openId: 'alpha',
      batchId: 'b1',
    })
    legs = applyFanOutLeg(legs, { id: 'alpha', status: 'running', batchId: 'b1' })
    legs = applyFanOutLeg(legs, { id: 'alpha', status: 'done', batchId: 'b1' })
    expect(legs).toHaveLength(1)
    expect(legs[0]).toMatchObject({
      id: 'alpha',
      label: 'Alpha',
      status: 'done',
      openId: 'alpha',
      batchId: 'b1',
    })
  })

  it('replaces the stack when a new batch starts', () => {
    const first = applyFanOutLeg([], {
      id: 'alpha',
      label: 'Alpha',
      status: 'done',
      batchId: 'b1',
    })
    const next = applyFanOutLeg(first, {
      id: 'bravo',
      label: 'Bravo',
      status: 'queued',
      batchId: 'b2',
    })
    expect(next.map((leg) => leg.id)).toEqual(['bravo'])
  })

  it('opens a CLI leg on the cli_agent seat, not a blueprint id', () => {
    const cards = cardsForFanOutLegs([
      { id: 'grok-cli', label: 'Grok CLI', status: 'running', kind: 'cli', openId: 'grok' },
    ])
    expect(cards[0].href).toBe('/chat?blueprint=cli_agent&mode=cli&cli=grok')
    expect(cards[0].external).toBe(false)
  })

  it('hides open for a remote leg with no href', () => {
    const cards = cardsForFanOutLegs([
      { id: 'hermes', label: 'Hermes', status: 'running', kind: 'remote' },
    ])
    expect(cards[0].href).toBeUndefined()
    expect(cards[0].live).toBe(true)
  })
})

describe('fan_out_leg frames', () => {
  it('parses a leg update', () => {
    const event = parseChatWsMessage(
      JSON.stringify({
        type: 'fan_out_leg',
        leg_id: 'hermes',
        label: 'Hermes',
        status: 'running',
        kind: 'remote',
        open_id: 'hermes',
        href: 'https://hermes.example/ui',
        batch_id: 'b9',
      }),
    )
    expect(event).toMatchObject({
      kind: 'fan_out_leg',
      id: 'hermes',
      label: 'Hermes',
      status: 'running',
      legKind: 'remote',
      href: 'https://hermes.example/ui',
      batchId: 'b9',
    })
  })

  it('cancel frame names only that leg id', () => {
    expect(JSON.parse(buildCancelFanOutLegFrame('bravo'))).toEqual({
      type: 'cancel_turn',
      leg_id: 'bravo',
    })
  })
})

describe('#1764 cardsForFanOutLegs excludeSeatIds', () => {
  it('drops the seat being talked to and keeps siblings', () => {
    const cards = cardsForFanOutLegs(
      [
        { id: 'codey', label: 'Codey', status: 'running', kind: 'cli', openId: 'codey', batchId: 'b1' },
        { id: 'stewie', label: 'Stewie', status: 'running', kind: 'cli', openId: 'stewie', batchId: 'b1' },
        { id: 'rue', label: 'Rue', status: 'running', kind: 'cli', openId: 'rue', batchId: 'b1' },
      ],
      { excludeSeatIds: ['codey'] },
    )
    expect(cards.map((c) => c.name)).toEqual(['Stewie', 'Rue'])
  })

  it('hides the whole stack when the only leg is this seat', () => {
    const cards = cardsForFanOutLegs(
      [{ id: 'codey', label: 'Codey', status: 'running', kind: 'cli', openId: 'codey', batchId: 'b1' }],
      { excludeSeatIds: ['codey'] },
    )
    expect(cards).toEqual([])
  })
})
