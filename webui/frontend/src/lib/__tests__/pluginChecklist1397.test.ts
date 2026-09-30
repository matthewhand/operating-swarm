import { describe, expect, it } from 'vitest'
import {
  MEMORY_ONLY_NOTE,
  checklistState,
  publicMemoryNamed,
  publicStatusFromPayload,
  selectedPack,
} from '../agentPluginPack'

describe('#1397 checklist states', () => {
  it('maps an enabled plugin to connected', () => {
    expect(checklistState('enabled')).toBe('connected')
    expect(checklistState('connected')).toBe('connected')
  })

  it('maps missing-auth to needsAuth', () => {
    expect(checklistState('missing-auth')).toBe('needsAuth')
    expect(checklistState('needsAuth')).toBe('needsAuth')
  })

  it('maps missing and missing-plugin to missing', () => {
    expect(checklistState('missing')).toBe('missing')
    expect(checklistState('missing-plugin')).toBe('missing')
    expect(checklistState('unknown')).toBe('missing')
  })

  it('keeps the three states on a scrubbed status payload', () => {
    const safe = publicStatusFromPayload({
      object: 'agent_plugins',
      agent_id: 'worker',
      plugins: [
        { pluginId: 'fetch', name: 'fetch', description: '', status: 'enabled' },
        { pluginId: 'github', name: 'github', description: '', status: 'missing-auth', required_env: ['GH_NAME'] },
        { pluginId: 'gone', name: 'gone', description: '', status: 'missing-plugin' },
      ],
      enabled: ['fetch'],
      missing: ['gone'],
      memory_named: [{ name: 'Desk notes', note: MEMORY_ONLY_NOTE, command: 'secret-helper' }],
    })
    expect(safe?.plugins.map((row) => checklistState(row.status))).toEqual([
      'connected',
      'needsAuth',
      'missing',
    ])
    expect(safe?.memory_named).toEqual([{ name: 'Desk notes', note: MEMORY_ONLY_NOTE }])
    expect(JSON.stringify(safe)).not.toContain('secret-helper')
  })

  it('drops credential-shaped memory names', () => {
    expect(publicMemoryNamed([{ name: 'sk-notarealkeyABCDEFGH' }])).toEqual([])
  })

  it('exports only the selected packable plugin ids', () => {
    const pack = selectedPack(
      [
        { pluginId: 'fetch', name: 'fetch', description: '' },
        { pluginId: 'web_search', name: 'web_search', description: '' },
      ],
      ['web_search'],
    )
    expect(pack.plugins.map((row) => row.pluginId)).toEqual(['web_search'])
  })
})
