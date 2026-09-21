import { describe, expect, it } from 'vitest'
import { isOpenMousBotKind, OPENMOUSBOT_LABEL, remoteKindLabel } from '../remoteKinds'

describe('remoteKindLabel', () => {
  it('labels omb as OpenMousBot and never OMB', () => {
    expect(remoteKindLabel('omb')).toBe(OPENMOUSBOT_LABEL)
    expect(remoteKindLabel('openmousbot')).toBe('OpenMousBot')
    expect(remoteKindLabel('hermes')).toBe('Hermes')
    expect(remoteKindLabel('rakazo')).toBe('Rakazo')
    expect(remoteKindLabel('herdr')).toBe('Herdr')
    expect(remoteKindLabel('omb')).not.toBe('OMB')
    expect(isOpenMousBotKind('omb')).toBe(true)
    expect(isOpenMousBotKind('hermes')).toBe(false)
  })
})
