import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  CONTEXT_USAGE_TYPE,
  formatContextUsageLabel,
  formatUsageBadgeLabel,
  formatUsageTokens,
  parseContextUsage,
  readUsageSpark,
  recordUsageSpark,
} from '../contextUsage'

describe('contextUsage', () => {
  afterEach(() => {
    window.sessionStorage.clear()
    vi.unstubAllGlobals()
  })

  it('formats the compact badge, including unknown windows', () => {
    expect(formatUsageTokens(12)).toBe('12')
    expect(formatUsageTokens(12300)).toBe('12.3k')
    expect(formatContextUsageLabel({ tokens: 12300, window: null })).toBe(
      '~12.3k tokens, window unknown',
    )
    expect(formatContextUsageLabel({ tokens: 12300, window: 128000 })).toBe('~12.3k / 128k')
  })

  it('parses a usage endpoint / ws payload', () => {
    expect(
      parseContextUsage({
        type: CONTEXT_USAGE_TYPE,
        conversation_id: 'c1',
        agent_id: 'jeeves',
        tokens: 40,
        window: 8192,
        pct: 0,
        estimate: true,
        last_output: 12,
        breakdown: { messages: 20, summaries: 10, system: 5, tools: 5 },
      }),
    ).toEqual({
      type: CONTEXT_USAGE_TYPE,
      conversation_id: 'c1',
      agent_id: 'jeeves',
      tokens: 40,
      window: 8192,
      pct: 0,
      estimate: true,
      last_output: 12,
      breakdown: { messages: 20, summaries: 10, system: 5, tools: 5 },
    })
    expect(parseContextUsage({ type: 'suggestions' })).toBeNull()
    expect(parseContextUsage({ data: [] })).toBeNull()
    expect(parseContextUsage({ tokens: 12 })).toBeNull()
  })

  it('defaults last_output to 0 on old payloads and formats the meter copy (#773)', () => {
    const parsed = parseContextUsage({
      type: CONTEXT_USAGE_TYPE,
      conversation_id: 'c1',
      agent_id: 'jeeves',
      tokens: 16000,
      window: 128000,
      pct: 13,
      estimate: true,
      breakdown: { messages: 15000, summaries: 0, system: 700, tools: 300 },
    })
    expect(parsed?.last_output).toBe(0)
    expect(formatUsageBadgeLabel(parsed!)).toBe('in ~16k / 128k tok')
    expect(
      formatUsageBadgeLabel({ ...parsed!, last_output: 320, estimate: false }),
    ).toBe('out 320 · in 16k / 128k tok')
    expect(
      formatUsageBadgeLabel({ ...parsed!, window: null }),
    ).toBe('in ~16k tok')
  })

  it('records a sparkline of context growth', () => {
    expect(readUsageSpark('c1')).toEqual([])
    expect(recordUsageSpark('c1', 10)).toEqual([10])
    expect(recordUsageSpark('c1', 20)).toEqual([10, 20])
    expect(readUsageSpark('c1')).toEqual([10, 20])
  })
})
