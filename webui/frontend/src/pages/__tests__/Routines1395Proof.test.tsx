/**
 * #1395 proof harness must not leave the SPA on a stubbed fetch.
 */
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Routines1395Proof, ROUTINES_1395_PROOF_PATH } from '../Routines1395Proof'

describe('Routines1395Proof harness', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.history.pushState({}, '', '/')
  })

  it('stubs routine fetches while mounted and restores window.fetch on unmount', async () => {
    const original = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ untouched: true }),
    })
    vi.stubGlobal('fetch', original)
    window.history.pushState({}, '', ROUTINES_1395_PROOF_PATH)

    const { unmount } = render(<Routines1395Proof />)
    expect(await screen.findByTestId('routine-list-status-r-watch')).toHaveTextContent('Pending fill')
    expect(original).not.toHaveBeenCalled()

    const stubbed = window.fetch
    unmount()
    expect(window.fetch).toBe(original)
    expect(window.fetch).not.toBe(stubbed)

    await window.fetch('/v1/agents/codey/routines/')
    expect(original).toHaveBeenCalledTimes(1)
  })
})
