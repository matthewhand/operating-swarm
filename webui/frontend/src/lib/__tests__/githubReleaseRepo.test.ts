/**
 * #1229 — the public repo slug defaults to the authoritative public mirror
 * `matthewhand/operating-swarm` (rebrand). Every call-home URL derives from
 * it; `VITE_SWARM_GITHUB_REPO` still overrides for forks/staging.
 */
import { describe, expect, it } from 'vitest'
import {
  GITHUB_API_LATEST,
  GITHUB_ISSUES_URL,
  GITHUB_RELEASES_URL,
  GITHUB_REPO,
} from '../githubRelease'

describe('#1229: default repo slug follows the rebrand', () => {
  it('defaults to matthewhand/operating-swarm', () => {
    expect(GITHUB_REPO).toBe('matthewhand/operating-swarm')
  })

  it('derives every call-home URL from that slug', () => {
    expect(GITHUB_ISSUES_URL).toBe('https://github.com/matthewhand/operating-swarm/issues')
    expect(GITHUB_RELEASES_URL).toBe('https://github.com/matthewhand/operating-swarm/releases')
    expect(GITHUB_API_LATEST).toBe(
      'https://api.github.com/repos/matthewhand/operating-swarm/releases/latest',
    )
  })
})
