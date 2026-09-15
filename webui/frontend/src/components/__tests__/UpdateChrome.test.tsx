import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react'
import UpdateChrome from '../UpdateChrome'
import { publishExpectedSpaVersion, resetExpectedSpaVersion } from '../../lib/spaHello'
import { setBakedSpaVersionForTests } from '../../lib/spaVersion'
import { GITHUB_ISSUES_URL, resetGithubReleaseCache } from '../../lib/githubRelease'

function stubGithub(tag: string | null) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('api.github.com') && tag) {
        return {
          ok: true,
          json: async () => ({
            tag_name: tag,
            html_url: `https://github.com/matthewhand/open-swarm/releases/tag/${tag}`,
          }),
        } as Response
      }
      return { ok: false, status: 503, json: async () => ({}) } as Response
    }),
  )
}

describe('UpdateChrome (REQ-78)', () => {
  beforeEach(() => {
    resetExpectedSpaVersion()
    resetGithubReleaseCache()
    setBakedSpaVersionForTests('0.5.4')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetExpectedSpaVersion()
    resetGithubReleaseCache()
    setBakedSpaVersionForTests(null)
  })

  it('match → ⓘ and click opens Issues (never stacks a cloud)', async () => {
    stubGithub('0.5.4')
    const openUrl = vi.fn()
    render(<UpdateChrome openUrl={openUrl} />)
    const btn = screen.getByTestId('rail-update-chrome')
    expect(btn).toHaveAttribute('data-kind', 'idle')
    expect(btn).toHaveAttribute('aria-label', 'Operating Swarm issues')
    fireEvent.click(btn)
    expect(openUrl).toHaveBeenCalledWith(GITHUB_ISSUES_URL)
    expect(screen.queryByTestId('rail-update-chrome')).toHaveAttribute('data-kind', 'idle')
  })

  it('SPA mismatch only → amber cloud and reload', async () => {
    stubGithub(null)
    const reload = vi.fn()
    const openUrl = vi.fn()
    render(<UpdateChrome reload={reload} openUrl={openUrl} />)
    act(() => {
      publishExpectedSpaVersion('0.5.5')
    })
    const btn = await screen.findByLabelText('Reload to update this tab')
    expect(btn).toHaveAttribute('data-kind', 'local')
    expect(btn).toHaveClass('os-rail-update-chrome--local')
    fireEvent.click(btn)
    expect(reload).toHaveBeenCalledTimes(1)
    expect(openUrl).not.toHaveBeenCalled()
  })

  it('GitHub newer only → sky cloud and release link', async () => {
    stubGithub('v0.5.6')
    const reload = vi.fn()
    const openUrl = vi.fn()
    render(<UpdateChrome reload={reload} openUrl={openUrl} />)
    act(() => {
      publishExpectedSpaVersion('0.5.4')
    })
    const btn = await screen.findByLabelText('Newer Operating Swarm release available')
    expect(btn).toHaveAttribute('data-kind', 'upstream')
    expect(btn).toHaveClass('os-rail-update-chrome--upstream')
    fireEvent.click(btn)
    expect(reload).not.toHaveBeenCalled()
    expect(openUrl).toHaveBeenCalledWith(
      'https://github.com/matthewhand/open-swarm/releases/tag/v0.5.6',
    )
  })

  it('API fail → no upstream cloud', async () => {
    stubGithub(null)
    render(<UpdateChrome />)
    act(() => {
      publishExpectedSpaVersion('0.5.4')
    })
    await waitFor(() => {
      expect(screen.getByTestId('rail-update-chrome')).toHaveAttribute('data-kind', 'idle')
    })
  })

  it('both → local priority, tooltip mentions upstream, one icon only', async () => {
    stubGithub('v0.5.6')
    const reload = vi.fn()
    render(<UpdateChrome reload={reload} />)
    act(() => {
      publishExpectedSpaVersion('0.5.5')
    })
    const btn = await screen.findByLabelText('Reload to update this tab')
    expect(btn).toHaveAttribute('data-kind', 'local')
    expect(btn).toHaveAttribute('data-also-upstream', 'true')
    expect(btn.getAttribute('title') || '').toMatch(/GitHub release/i)
    expect(btn.querySelectorAll('svg')).toHaveLength(1)
    fireEvent.click(btn)
    expect(reload).toHaveBeenCalledTimes(1)
  })
})
