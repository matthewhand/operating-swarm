import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { TOOL_MEMORIES, TOOL_OPEN_PULL_REQUEST } from '../routines'
import * as mirror from '../routineToolSuggestions'
import {
  SUGGESTABLE_TOOL_LABELS,
  instructionFingerprint,
  visibleToolSuggestions,
} from '../routineToolSuggestions'

/**
 * Everything below goes through `visibleToolSuggestions` — the only entry point
 * `RoutineToolSuggestions.tsx` calls. `suggestRoutineTools` is deliberately not
 * exported (#1669): a second public entry point is a second thing to keep in
 * sync, and nothing in the product used it.
 */
const rows = (
  instruction: string,
  tools: string[] = [],
  trigger: Parameters<typeof visibleToolSuggestions>[2] = null,
  dismissed: Record<string, string> = {},
) => visibleToolSuggestions(instruction, tools, trigger, dismissed)

const MODULE_SOURCE = readFileSync(join(__dirname, '..', 'routineToolSuggestions.ts'), 'utf8')

/** Strip comments so a symbol named in prose cannot satisfy or trip a check. */
const MODULE_CODE = MODULE_SOURCE
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/(^|[^:])\/\/[^\n]*/g, '$1')

describe('routine tool suggestions (#1410)', () => {
  it('mentions a PR and suggests Open Pull Request', () => {
    const found = rows('Investigate the issue and open a pull request.')
    expect(found.map((row) => row.id)).toEqual([TOOL_OPEN_PULL_REQUEST])
    expect(found[0].reason).toBe('Instructions mention opening a PR — add Open Pull Request?')
    expect(found[0].auto_enable).toBe(false)
    expect(found[0].destructive).toBe(true)
  })

  it('mentions memory / MEMORIES and suggests Memories', () => {
    const found = rows('Remember prior context from MEMORIES.')
    expect(found.map((row) => row.id)).toEqual([TOOL_MEMORIES])
    expect(found[0].reason).toBe('Instructions mention memory — add Memories?')
  })

  it('does not invent a Slack tool id', () => {
    expect(rows('Post the recap to Slack.')).toEqual([])
  })

  it('does not treat bare remember as the Memories tool', () => {
    expect(rows('Remember to file the weekly report.').map((row) => row.id)).not.toContain(
      TOOL_MEMORIES,
    )
  })

  it('does not nag when the tools are already present', () => {
    expect(
      rows('Open a PR and remember prior context from MEMORIES.', [
        TOOL_OPEN_PULL_REQUEST,
        TOOL_MEMORIES,
      ]),
    ).toEqual([])
  })

  it('does not suggest again when the present id differs only by case', () => {
    expect(rows('Please open a PR.', ['Open_Pull_Request'])).toEqual([])
  })

  it('honors a negation split across lines', () => {
    const found = rows('Investigate the issue.\nDo not\nopen a pull request.')
    expect(found.map((row) => row.id)).not.toContain(TOOL_OPEN_PULL_REQUEST)
  })

  it('does not suggest Open PR when instructions forbid it', () => {
    const found = rows('Investigate the issue. Do not open a pull request.')
    expect(found.map((row) => row.id)).not.toContain(TOOL_OPEN_PULL_REQUEST)
  })

  it('optionally uses a pull_request trigger as a signal', () => {
    const found = rows('Review the incoming change.', [], {
      kind: 'github_event',
      event_type: 'pull_request.opened',
      owner_repo: 'owner/repo',
    } as never)
    expect(found.map((row) => row.id)).toEqual([TOOL_OPEN_PULL_REQUEST])
  })

  it('does not treat github_pr_merged kind as an Open PR hint', () => {
    const found = rows('Summarize what landed.', [], {
      kind: 'github_pr_merged',
      owner_repo: 'owner/repo',
      event: 'merged',
      actor: 'anyone',
    } as never)
    expect(found).toEqual([])
  })

  it('never copies token-shaped instruction text into the reason', () => {
    const token = 'ghp_[REDACTED:GitHub token]'
    const found = rows(`Open a PR. Auth ${token}`)
    expect(JSON.stringify(found)).not.toContain(token)
    expect(JSON.stringify(found)).not.toContain('ghp_')
    expect(found[0].reason).toBe('Instructions mention opening a PR — add Open Pull Request?')
  })

  it('never auto-enables a destructive tool', () => {
    // #1669 removed the `applySuggestedTool` twin of Python's
    // `apply_suggested_tool`: the product never called it (RoutineToolsFields
    // dedupes itself) so it was a second, never-exercised confirm gate. The
    // invariant that matters is now structural — the payload carries no
    // imperative field, and the module exports nothing that can mutate `tools`.
    const found = rows('Open a PR and remember prior context from MEMORIES.')
    expect(found.every((row) => row.auto_enable === false)).toBe(true)
    expect(Object.keys(found[0]).sort()).toEqual([
      'auto_enable',
      'destructive',
      'id',
      'label',
      'reason',
    ])
    // Runtime exports only — `RoutineToolSuggestion` is type-only. Pinning the
    // whole surface means a new exported helper has to be a deliberate choice.
    expect(Object.keys(mirror).sort()).toEqual([
      'SUGGESTABLE_TOOL_LABELS',
      'instructionFingerprint',
      'visibleToolSuggestions',
    ])
  })

  it('exposes no apply/confirm mutator and no second suggestion entry point', () => {
    // Guards the #1669 deletion. Reintroducing either name fails here.
    expect('applySuggestedTool' in mirror).toBe(false)
    expect('suggestRoutineTools' in mirror).toBe(false)
    expect(MODULE_CODE).not.toMatch(/export\s+function\s+apply\w*/)
    expect(MODULE_CODE).not.toMatch(/^export\s+function\s+suggest\w*/m)
  })

  it('does not reimplement the server-side confidence ranker (#1454)', () => {
    // The ranker has one home: `rank_tools_by_confidence` in Python. A second
    // client-side scorer would be the divergence #1669 is about.
    for (const symbol of ['confidence', 'scorer', 'rank_tools', 'lexical_tool_confidence']) {
      expect(MODULE_CODE).not.toContain(symbol)
    }
  })

  it('keeps a dismiss for the current draft until instructions change materially', () => {
    const instruction = 'Please open a PR.'
    const dismissed = { [TOOL_OPEN_PULL_REQUEST]: instructionFingerprint(instruction) }
    expect(visibleToolSuggestions(instruction, [], null, dismissed)).toEqual([])
    expect(visibleToolSuggestions('Please open a PR!', [], null, dismissed)).toEqual([])
    const again = visibleToolSuggestions(
      'Please open a PR and also remember MEMORIES.',
      [],
      null,
      dismissed,
    )
    expect(again.map((row) => row.id)).toEqual([TOOL_OPEN_PULL_REQUEST, TOOL_MEMORIES])
  })

  it('labels the suggestable tools for the catalog fallback', () => {
    expect(SUGGESTABLE_TOOL_LABELS[TOOL_OPEN_PULL_REQUEST]).toBe('Open Pull Request')
    expect(SUGGESTABLE_TOOL_LABELS[TOOL_MEMORIES]).toBe('Memories')
  })
})
