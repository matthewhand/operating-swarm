import { describe, expect, it } from 'vitest'
import {
  engineSwitchCapabilityWarning,
  enabledSeatCapabilities,
  formatEngineSwitchWarning,
  lostEngineCapabilities,
} from '../engineSwitchWarning'

describe('#1324 engine switch capability warning', () => {
  it('stays silent when CLI hop rows are equal', () => {
    const row = { export: 'summary', list: 'works', resume: true }
    expect(
      lostEngineCapabilities({
        fromKind: 'cli',
        toKind: 'cli',
        fromRow: row,
        toRow: row,
      }),
    ).toEqual([])
    expect(
      engineSwitchCapabilityWarning({
        fromKind: 'cli',
        toKind: 'cli',
        fromRow: row,
        toRow: row,
        fromLabel: 'grok',
        toLabel: 'agy',
      }),
    ).toBeNull()
  })

  it('names session list when list capability drops', () => {
    const lost = lostEngineCapabilities({
      fromKind: 'cli',
      toKind: 'cli',
      fromRow: { export: 'summary', list: 'works', resume: true },
      toRow: { export: 'summary', list: 'paste-only', resume: true },
    })
    expect(lost).toEqual(['list'])
    const warning = formatEngineSwitchWarning(lost, 'grok', 'claude')
    expect(warning).toBe('Switching from grok to claude loses session list.')
    expect(warning).not.toMatch(/REQ-|#\d+/)
  })

  it('treats native transcript export as the only export loss', () => {
    expect(
      lostEngineCapabilities({
        fromKind: 'cli',
        toKind: 'cli',
        fromRow: { export: 'transcript', list: 'works', resume: true },
        toRow: { export: 'summary', list: 'works', resume: true },
      }),
    ).toContain('export')
    expect(
      lostEngineCapabilities({
        fromKind: 'cli',
        toKind: 'cli',
        fromRow: { export: 'summary', list: 'works', resume: true },
        toRow: { export: 'none', list: 'works', resume: true },
      }),
    ).toEqual([])
  })

  it('warns API → CLI seat losses and stays quiet on the reverse', () => {
    expect(lostEngineCapabilities({ fromKind: 'api', toKind: 'cli' })).toEqual([
      'attach',
      'compact',
      'plugins',
      'routines',
      'parallel_fan_out',
    ])
    expect(lostEngineCapabilities({ fromKind: 'cli', toKind: 'api' })).toEqual([])
    const warning = engineSwitchCapabilityWarning({
      fromKind: 'api',
      toKind: 'cli',
      fromLabel: 'API gateway',
      toLabel: 'grok',
    })
    expect(warning).toMatch(/file attachments/)
    expect(warning).toMatch(/plugins/)
    expect(warning).toMatch(/^Switching from API gateway to grok loses /)
  })

  it('does not score an API destination as a fake catalog CLI', () => {
    expect(
      lostEngineCapabilities({
        fromKind: 'cli',
        toKind: 'api',
        fromRow: { export: 'transcript', list: 'works', resume: true },
        toRow: { export: 'none', list: 'unsupported', resume: false },
      }),
    ).toEqual([])
  })

  it('treats WebGPU as offering no seat capabilities', () => {
    expect(enabledSeatCapabilities('webgpu')).toEqual([])
    const lost = lostEngineCapabilities({ fromKind: 'api', toKind: 'webgpu' })
    expect(lost).toEqual(expect.arrayContaining(['attach', 'plugins', 'routines']))
  })

  it('joins three-or-more losses with an oxford comma', () => {
    expect(formatEngineSwitchWarning(['attach', 'plugins', 'routines'], 'API', 'grok')).toBe(
      'Switching from API to grok loses file attachments, plugins, and routines.',
    )
  })
})
