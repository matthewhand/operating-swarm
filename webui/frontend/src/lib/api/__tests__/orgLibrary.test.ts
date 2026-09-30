/**
 * #1311 — org-shared library client: list presets, publish, whole-team share.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  fetchOrgLibrary,
  publishOrgLibraryBot,
  shareOrgLibraryBotWithTeam,
} from '../orgLibrary'

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('org library client (#1311)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('lists org-shared bots including presets', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(
        {
          object: 'list',
          data: [
            {
              id: 'preset-support',
              object: 'org_library.bot',
              name: 'Support',
              preset: true,
              visibility: 'org',
            },
          ],
        },
        200,
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const listed = await fetchOrgLibrary()
    expect(listed.data[0]?.id).toBe('preset-support')
    expect(listed.data[0]?.preset).toBe(true)
    expect(String(fetchMock.mock.calls[0][0])).toContain('/v1/org-library/')
  })

  it('filters the library by team_id', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ object: 'list', data: [] }, 200))
    vi.stubGlobal('fetch', fetchMock)
    await fetchOrgLibrary('eng')
    expect(String(fetchMock.mock.calls[0][0])).toContain('team_id=eng')
  })

  it('publishes a bot recipe to the org library', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ id: 'account-health', object: 'org_library.bot', visibility: 'org' }, 201),
    )
    vi.stubGlobal('fetch', fetchMock)
    const created = await publishOrgLibraryBot({ name: 'Account Health' })
    expect(created.id).toBe('account-health')
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(JSON.parse(String(init.body))).toEqual({ name: 'Account Health' })
  })

  it('shares a bot with a whole team', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(
        {
          object: 'org_library.share',
          scope: 'team',
          team_id: 'eng',
          roster_id: 'eng',
          bot: { id: 'bug-repro', visibility: 'team', team_ids: ['eng'] },
        },
        200,
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    const shared = await shareOrgLibraryBotWithTeam('bug-repro', 'eng')
    expect(shared.scope).toBe('team')
    expect(shared.team_id).toBe('eng')
    expect(String(fetchMock.mock.calls[0][0])).toContain('/v1/org-library/bug-repro/share/')
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(JSON.parse(String(init.body))).toEqual({ scope: 'team', team_id: 'eng' })
  })
})
