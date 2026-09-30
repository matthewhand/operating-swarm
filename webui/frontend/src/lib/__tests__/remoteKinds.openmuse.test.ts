import { describe, expect, it } from 'vitest'
import {
  isOpenMousBotKind,
  OPENMOUSBOT_LABEL,
  OPENMUSE_LABEL,
  remoteKindLabel,
  remoteQuietSubtitle,
} from '../remoteKinds'

describe('OpenMuse kind label', () => {
  it('labels openmuse as OpenMuse, distinct from OpenMousBot', () => {
    expect(OPENMUSE_LABEL).toBe('OpenMuse')
    expect(remoteKindLabel('openmuse')).toBe('OpenMuse')
    // The two products share a name prefix and nothing else. A shared-prefix
    // collision that read "OpenMousBot" for an OpenMuse seat would send the
    // operator to the wrong server entirely.
    expect(remoteKindLabel('openmuse')).not.toBe(OPENMOUSBOT_LABEL)
    expect(remoteKindLabel('omb')).toBe(OPENMOUSBOT_LABEL)
  })

  it('is not mistaken for OpenMousBot by the kind predicate', () => {
    expect(isOpenMousBotKind('openmuse')).toBe(false)
    expect(isOpenMousBotKind('openmuse-lab')).toBe(false)
    expect(isOpenMousBotKind('omb')).toBe(true)
  })

  it('resolves the open-muse / open_muse spelling variants', () => {
    expect(remoteKindLabel('open-muse')).toBe('OpenMuse')
    expect(remoteKindLabel('open_muse')).toBe('OpenMuse')
    expect(remoteKindLabel('OPENMUSE')).toBe('OpenMuse')
  })

  it('shows OpenMuse as a named-instance subtitle', () => {
    expect(remoteQuietSubtitle({ kind: 'openmuse', title: 'Lab box' })).toBe('OpenMuse')
    expect(remoteQuietSubtitle({ kind: 'openmuse', title: 'OpenMuse' })).toBe('Remote')
  })

  it('still falls back for an unknown kind', () => {
    expect(remoteKindLabel('openmuseish', 'Custom')).toBe('Custom')
  })
})
