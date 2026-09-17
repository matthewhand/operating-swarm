import { describe, expect, it } from 'vitest'
import {
  DEMO_FALLBACK_NOTICE,
  DEMO_SCENARIOS,
  TOUR_PROMPT,
  demoFramesForPrompt,
  demoSuggestionChips,
  matchDemoScenario,
} from '../scenarios'

describe('demo scenarios (REQ-882)', () => {
  it('covers the four showcases plus tour', () => {
    const ids = DEMO_SCENARIOS.map((row) => row.id)
    expect(ids).toEqual(expect.arrayContaining(['sdlc', 'cli', 'remote', 'team', 'tour']))
  })

  it('matches chips and keywords', () => {
    expect(matchDemoScenario('Build a REST API with the SDLC team').id).toBe('sdlc')
    expect(matchDemoScenario('please run pytest in the git repo').id).toBe('cli')
    expect(matchDemoScenario('ping hermes telemetry').id).toBe('remote')
    expect(matchDemoScenario(TOUR_PROMPT).id).toBe('tour')
  })

  it('falls back with the public-demo notice', () => {
    const row = matchDemoScenario('Write a poem about rust')
    expect(row.id).toBe('fallback')
    expect(row.body).toContain(DEMO_FALLBACK_NOTICE)
  })

  it('streams status + chunks for CLI', () => {
    const frames = demoFramesForPrompt('Simulate a CLI git refactor')
    expect(frames.some((f) => f.kind === 'status')).toBe(true)
    expect(frames.some((f) => f.kind === 'chunk')).toBe(true)
    const body = frames.filter((f) => f.kind === 'chunk').map((f) => f.text).join('')
    expect(body).toContain('pytest')
  })

  it('exposes composer chips', () => {
    const chips = demoSuggestionChips()
    expect(chips).toContain('Play the guided tour')
    expect(chips.length).toBe(DEMO_SCENARIOS.length)
  })
})
