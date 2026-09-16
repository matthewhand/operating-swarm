import { describe, expect, it } from 'vitest'
import {
  KNOWN_CLI_NAMES,
  cliSelectPlaceholder,
  compactCliRows,
  configuredCliNames,
  discoveredCliNames,
  focusedCliName,
  suggestedCliEntries,
} from '../cliAgents'

describe('cli agents catalog (REQ-157)', () => {
  it('documents the known host CLIs', () => {
    expect(KNOWN_CLI_NAMES).toEqual([
      'agy',
      'claude',
      'codex',
      'gemini',
      'grok',
      'opencode',
      'pi',
    ])
  })

  it('treats a fresh payload as empty configured with PATH suggestions', () => {
    const empty = {
      clis: [...KNOWN_CLI_NAMES],
      configured: [],
      discovered: ['grok', 'agy'],
      installed: ['grok', 'agy'],
      suggestions: {
        grok: { cmd: ['grok', '-p', '{prompt}'] },
        agy: { cmd: ['agy', '-p={prompt}'] },
      },
      native_consensus: {},
      catalog: {},
    }
    expect(configuredCliNames(empty)).toEqual([])
    expect(discoveredCliNames(empty)).toEqual(['grok', 'agy'])
    expect(suggestedCliEntries(empty).map((row) => row.name)).toEqual(['agy', 'grok'])
    expect(cliSelectPlaceholder(0, '')).toBe('No CLI agents')
  })

  it('drops a configured name from suggestions and keeps PATH discovery', () => {
    const listed = {
      clis: [...KNOWN_CLI_NAMES],
      configured: ['grok'],
      discovered: ['grok', 'claude'],
      suggestions: {
        claude: { cmd: ['claude', '-p', '{prompt}'] },
      },
      native_consensus: {},
      catalog: {},
    }
    expect(configuredCliNames(listed)).toEqual(['grok'])
    expect(suggestedCliEntries(listed).map((row) => row.name)).toEqual(['claude'])
    expect(cliSelectPlaceholder(1, '')).toBe('Pick a CLI')
  })

  it('builds a compact list and hides unavailable until asked', () => {
    const listed = {
      clis: [...KNOWN_CLI_NAMES],
      known: [...KNOWN_CLI_NAMES],
      configured: ['grok'],
      discovered: ['grok', 'claude'],
      suggestions: {
        claude: { cmd: ['claude', '-p', '{prompt}'] },
      },
      native_consensus: {},
      catalog: { grok: { cmd: ['grok'] } },
    }
    const compact = compactCliRows(listed, { grok: { cmd: ['grok', '-p', '{prompt}'] } })
    expect(compact.map((row) => [row.name, row.status])).toEqual([
      ['grok', 'configured'],
      ['claude', 'detected'],
    ])
    const withUnavailable = compactCliRows(listed, { grok: { cmd: ['grok'] } }, { showUnavailable: true })
    expect(withUnavailable.some((row) => row.name === 'pi' && row.status === 'not-detected')).toBe(true)
    expect(focusedCliName('cli:grok')).toBe('grok')
    expect(focusedCliName('llm:local')).toBeNull()
  })
})
