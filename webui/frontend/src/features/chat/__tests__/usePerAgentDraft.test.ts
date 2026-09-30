/**
 * #1331 — per-agent composer drafts: the store contract.
 *
 * Two agents, type in A, switch to B (empty), type in B, switch back to A
 * (A intact); reload restores both; a cleared draft stays cleared.
 */
import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  AGENT_DRAFTS_STORAGE_KEY,
  __resetAgentDraftsForTests,
  getAgentDraft,
  setAgentDraft,
  usePerAgentDraft,
} from '../usePerAgentDraft'

vi.mock('../../../lib/userPrefs', () => ({
  fetchUserPrefs: vi.fn(async () => null),
  saveUserPrefs: vi.fn(async () => null),
}))

describe('#1331 usePerAgentDraft', () => {
  beforeEach(() => {
    __resetAgentDraftsForTests()
  })

  it('keeps each agent draft in its own slot across a switch', () => {
    const { result, rerender } = renderHook(({ id }: { id: string }) => usePerAgentDraft(id), {
      initialProps: { id: 'agent-a' },
    })

    act(() => result.current[1]('draft for A'))
    expect(result.current[0]).toBe('draft for A')

    rerender({ id: 'agent-b' })
    expect(result.current[0]).toBe('')

    act(() => result.current[1]('draft for B'))
    expect(result.current[0]).toBe('draft for B')

    rerender({ id: 'agent-a' })
    expect(result.current[0]).toBe('draft for A')

    rerender({ id: 'agent-b' })
    expect(result.current[0]).toBe('draft for B')
  })

  it('persists to localStorage and restores both on reload (fresh module)', async () => {
    setAgentDraft('agent-a', 'alpha')
    setAgentDraft('agent-b', 'beta')
    expect(window.localStorage.getItem(AGENT_DRAFTS_STORAGE_KEY)).toContain('alpha')

    vi.resetModules()
    const fresh = await import('../usePerAgentDraft')
    expect(fresh.getAgentDraft('agent-a')).toBe('alpha')
    expect(fresh.getAgentDraft('agent-b')).toBe('beta')
  })

  it('a cleared draft is persisted and never resurrects', () => {
    const { result, rerender } = renderHook(({ id }: { id: string }) => usePerAgentDraft(id), {
      initialProps: { id: 'agent-a' },
    })
    act(() => result.current[1]('temporary'))
    act(() => result.current[1](''))

    rerender({ id: 'agent-b' })
    rerender({ id: 'agent-a' })
    expect(result.current[0]).toBe('')
    expect(getAgentDraft('agent-a')).toBe('')

    // Reload: the explicit clear is what localStorage holds.
    expect(JSON.parse(window.localStorage.getItem(AGENT_DRAFTS_STORAGE_KEY) ?? '{}')).toEqual({
      'agent-a': '',
    })
  })

  it('supports the updater-function form used by voice / typing-anywhere', () => {
    const { result } = renderHook(() => usePerAgentDraft('agent-a'))
    act(() => result.current[1]((prev) => prev + 'h'))
    act(() => result.current[1]((prev) => prev + 'i'))
    expect(result.current[0]).toBe('hi')
    expect(getAgentDraft('agent-a')).toBe('hi')
  })

  it('normalizes an empty agent id to the default agent slot', () => {
    setAgentDraft('', 'support draft')
    expect(getAgentDraft('')).toBe('support draft')
    expect(getAgentDraft('_default')).toBe('support draft')
  })
})
