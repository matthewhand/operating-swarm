/**
 * #1324 — capabilityDelta compares declared seat rows, not kind === 'api'.
 */
import { describe, expect, it } from 'vitest'
import {
  capabilityDelta,
  capabilitySideFromDirectory,
  type SeatCapabilityDirectory,
} from '../seatRouting'

const DIRECTORY: SeatCapabilityDirectory = {
  object: 'seat_capabilities',
  labels: {
    attach: 'file attachments',
    compact: 'thread compact',
    plugins: 'plugins',
    routines: 'routines',
    list: 'session list',
    resume: 'session resume',
    export: 'native transcript export',
  },
  seat_capabilities: {
    api: {
      attach: { enabled: true, label: 'shared files' },
      compact: { enabled: true, label: 'thread compact' },
      plugins: { enabled: true, label: 'plugins' },
      routines: { enabled: true, label: 'routines' },
      coordination: { enabled: false },
    },
    cli: {
      attach: { enabled: false },
      compact: { enabled: false },
      plugins: { enabled: false },
      routines: { enabled: false },
      coordination: { enabled: false },
    },
    remote: {
      attach: { enabled: false },
      compact: { enabled: false },
      plugins: { enabled: false },
      routines: { enabled: false },
      coordination: { enabled: false },
    },
  },
  cli: {
    grok: { list: 'works', resume: true, export: 'summary', label: 'grok' },
    claude: { list: 'paste-only', resume: true, export: 'summary', label: 'claude' },
    agy: { list: 'works', resume: true, export: 'summary', label: 'agy' },
  },
}

function side(kind: string, id: string, label = id) {
  return capabilitySideFromDirectory(DIRECTORY, { kind, id, label })
}

describe('#1324 capabilityDelta', () => {
  it('names a CLI session-list loss from declared hop rows', () => {
    const delta = capabilityDelta(side('cli', 'grok'), side('cli', 'claude'))
    expect(delta.lost).toEqual(['list'])
    expect(delta.warning).toBe('Switching from grok to claude loses session list.')
  })

  it('stays silent when the destination is equal or stronger', () => {
    expect(capabilityDelta(side('cli', 'grok'), side('cli', 'agy')).warning).toBeNull()
    expect(capabilityDelta(side('cli', 'grok'), side('api', 'api_agent', 'API')).warning).toBeNull()
  })

  it('uses the declared axis label, not a kind === api guess', () => {
    const delta = capabilityDelta(side('api', 'api_agent', 'API'), side('cli', 'grok', 'grok'))
    expect(delta.lost).toEqual(['attach', 'compact', 'plugins', 'routines'])
    expect(delta.warning).toBe(
      'Switching from API to grok loses shared files, thread compact, plugins, and routines.',
    )
    expect(delta.warning).not.toContain('file attachments')
  })

  it('reports a declared axis that is not in the historical seat list', () => {
    const withSandbox: SeatCapabilityDirectory = {
      ...DIRECTORY,
      seat_capabilities: {
        ...DIRECTORY.seat_capabilities,
        api: {
          ...DIRECTORY.seat_capabilities.api,
          sandbox: { enabled: true, label: 'sandbox files' },
        },
      },
    }
    const from = capabilitySideFromDirectory(withSandbox, {
      kind: 'api',
      id: 'api_agent',
      label: 'API',
    })
    const to = capabilitySideFromDirectory(withSandbox, { kind: 'cli', id: 'grok', label: 'grok' })
    const delta = capabilityDelta(from, to)
    expect(delta.lost).toContain('sandbox')
    expect(delta.warning).toContain('sandbox files')
  })
})
