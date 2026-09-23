/**
 * #856 slice A — `lib/api.ts` becomes the `lib/api/` package without a
 * single import-path change: a directory named `api` resolves for every
 * existing `'./api'` / `'../lib/api'` specifier.
 *
 * Pinned contract (the doctrine of the split):
 * 1. the package re-exports the transport kernel verbatim (errors, verb
 *    helpers, provenance) — same names, same behavior;
 * 2. domain modules re-export their slice (agents/remotes/teams/…);
 * 3. `api.ts` (the old file) is gone — the directory *is* the module;
 * 4. no behavior change: throttle classification and client-source
 *    provenance act identically through the new entry points.
 */
import { describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  ApiAuthError,
  ApiThrottleError,
  isAuthError,
  isThrottleError,
  apiGet,
  apiPost,
  withClientSource,
  fetchBlueprints,
  fetchRemotes,
  operateRemote,
  fetchTeams,
  fetchLlmProfiles,
  fetchHerdrAgents,
  fetchCliAgents,
  fetchSpeechSettings,
  fetchMcpPlugins,
  AUTH_ERROR_EVENT,
} from '../api'
import * as clientModule from '../api/client'
import * as remotesModule from '../api/remotes'

describe('#856 slice A: lib/api package resolves the same surface', () => {
  it('re-exports the transport kernel', () => {
    expect(ApiError).toBe(clientModule.ApiError)
    expect(ApiAuthError).toBe(clientModule.ApiAuthError)
    expect(ApiThrottleError).toBe(clientModule.ApiThrottleError)
    expect(AUTH_ERROR_EVENT).toBe(clientModule.AUTH_ERROR_EVENT)
    expect(typeof apiGet).toBe('function')
    expect(typeof apiPost).toBe('function')
  })

  it('keeps error identity through instanceof guards', () => {
    const err = new ApiThrottleError(429, 'slow down', 12)
    expect(isThrottleError(err)).toBe(true)
    expect(err.retryAfterSeconds).toBe(12)
    expect(isAuthError(new ApiAuthError(401, 'nope'))).toBe(true)
    expect(isAuthError(err)).toBe(false)
  })

  it('re-exports domain functions bound to their home module', () => {
    expect(fetchRemotes).toBe(remotesModule.fetchRemotes)
    expect(operateRemote).toBe(remotesModule.operateRemote)
    expect(typeof fetchBlueprints).toBe('function')
    expect(typeof fetchTeams).toBe('function')
    expect(typeof fetchLlmProfiles).toBe('function')
    expect(typeof fetchHerdrAgents).toBe('function')
    expect(typeof fetchCliAgents).toBe('function')
    expect(typeof fetchSpeechSettings).toBe('function')
    expect(typeof fetchMcpPlugins).toBe('function')
  })

  it('preserves throttle classification through apiGet (no raw DRF prose)', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ detail: 'Request was throttled. Expected available in 12 seconds.' }),
        { status: 429, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    try {
      await expect(apiGet('/v1/anything/')).rejects.toBeInstanceOf(ApiThrottleError)
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('preserves caller provenance through withClientSource', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true })))
    vi.stubGlobal('fetch', fetchMock)
    try {
      await withClientSource('TestSource', () => apiPost('/v1/anything/', { a: 1 }))
      const headers = fetchMock.mock.calls[0][1].headers as Record<string, string>
      expect(headers['X-Swarm-Client-Source']).toBe('TestSource')
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
