import { describe, expect, it } from 'vitest'
import {
  UNASSIGNED_RIG,
  agentRigAddress,
  formatRigAddress,
  parseRigAddress,
  sectionRigName,
} from '../rigAddress'
import type { RailSectionsState } from '../railSections'

const sections: RailSectionsState = {
  sections: [
    { id: 'sec_local', name: 'local' },
    { id: 'sec_blank', name: '' },
  ],
  membership: { 'skeptic_a': 'sec_local', 'quiet': 'sec_blank' },
}

describe('#1224 rig addresses', () => {
  it('parses qualified and bare addresses', () => {
    expect(parseRigAddress('skeptic@local')).toEqual({ role: 'skeptic', rig: 'local' })
    expect(parseRigAddress('skeptic')).toEqual({ role: 'skeptic' })
    expect(parseRigAddress('  skeptic@ops  ')).toEqual({ role: 'skeptic', rig: 'ops' })
    expect(parseRigAddress('')).toBeNull()
    expect(parseRigAddress(null)).toBeNull()
    expect(parseRigAddress('role@rig@extra')).toBeNull()
    expect(parseRigAddress('@local')).toBeNull()
    expect(parseRigAddress('skeptic@')).toBeNull()
  })

  it('formats with and without a rig', () => {
    expect(formatRigAddress('skeptic', 'local')).toBe('skeptic@local')
    expect(formatRigAddress('skeptic')).toBe('skeptic')
    expect(formatRigAddress('skeptic', '')).toBe('skeptic')
  })

  it('resolves a dynamic rig name from section membership', () => {
    expect(sectionRigName('skeptic_a', sections)).toBe('local')
    expect(sectionRigName('quiet', sections)).toBe('sec_blank')
    expect(sectionRigName('stranger', sections)).toBeUndefined()
  })

  it('prefers the static team rig over a dynamic section', () => {
    expect(
      agentRigAddress({ role: 'skeptic', rig: 'factory', sectionRig: 'local' }),
    ).toBe('skeptic@factory')
    expect(agentRigAddress({ role: 'skeptic', sectionRig: 'local' })).toBe(
      'skeptic@local',
    )
  })

  it('falls back to a bare role or @unassigned', () => {
    expect(agentRigAddress({ role: 'skeptic' })).toBe('skeptic')
    expect(agentRigAddress({ role: 'skeptic', showUnassigned: true })).toBe(
      `skeptic@${UNASSIGNED_RIG}`,
    )
  })
})
