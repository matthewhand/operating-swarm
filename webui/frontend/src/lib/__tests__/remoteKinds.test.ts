import { describe, expect, it } from 'vitest'
import {
  isOpenMousBotKind,
  OPENMOUSBOT_LABEL,
  remoteKindLabel,
  remoteQuietSubtitle,
  remoteRailDetail,
} from '../remoteKinds'

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

  it('labels each remote kind, and does not call unknown kinds OpenMousBot', () => {
    expect(remoteKindLabel('trueforge')).toBe('TrueForge')
    expect(remoteKindLabel('true-forge')).toBe('TrueForge')
    expect(remoteKindLabel('openmausbot')).toBe('OpenMousBot')
    expect(remoteKindLabel('anything-llm')).toBe('AnythingLLM')
    expect(remoteKindLabel('open-swarm')).toBe('open-swarm')
    expect(remoteKindLabel('openswarm')).toBe('open-swarm')
    expect(remoteKindLabel('open_swarm')).toBe('open-swarm')
    expect(remoteKindLabel('dsh', 'DeepSeek Harness')).toBe('DeepSeek Harness')
    expect(remoteKindLabel('custom-harness')).toBe('custom-harness')
    expect(remoteKindLabel('custom-harness')).not.toBe('OpenMousBot')
    expect(remoteKindLabel('')).toBe('')
    expect(isOpenMousBotKind('openmaus')).toBe(true)
    expect(isOpenMousBotKind('trueforge')).toBe(false)
  })

  it('does not repeat a kind title, ignoring case', () => {
    expect(remoteQuietSubtitle({ kind: 'trueforge', title: 'TrueForge' })).toBe('Remote')
    expect(remoteQuietSubtitle({ kind: 'trueforge', title: 'trueforge' })).toBe('Remote')
    expect(remoteQuietSubtitle({ kind: 'trueforge', title: 'Forge B' })).toBe('TrueForge')
    expect(remoteQuietSubtitle({ kind: 'trueforge', title: 'Forge B', description: 'lab' })).toBe('lab')
  })

  it('#1436: rail detail is never the Remote team fallback', () => {
    expect(remoteRailDetail({ kind: 'herdr', title: 'Desk' })).toBe('Herdr')
    expect(remoteRailDetail({ kind: 'herdr', title: 'Herdr' })).toBe('')
    expect(remoteRailDetail({ kind: 'herdr', title: 'herdr' })).toBe('')
    expect(remoteRailDetail({ kind: 'omb', title: 'Gate' }, 'last turn')).toBe('last turn')
    expect(remoteRailDetail({ kind: 'custom', title: 'Gate', description: 'LAN bridge' })).toBe(
      'LAN bridge',
    )
    expect(remoteRailDetail({ kind: 'herdr', title: 'Desk' })).not.toBe('Remote team')
  })
})
