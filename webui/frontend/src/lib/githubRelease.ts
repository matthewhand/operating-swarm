/**
 * Public GitHub call-home for a newer open-swarm release (REQ-78).
 * Unauthenticated only. Failure → no upstream signal. No tokens.
 */

export const GITHUB_REPO =
  import.meta.env.VITE_SWARM_GITHUB_REPO || 'matthewhand/open-swarm'
export const GITHUB_ISSUES_URL = `https://github.com/${GITHUB_REPO}/issues`
export const GITHUB_RELEASES_URL = `https://github.com/${GITHUB_REPO}/releases`
export const GITHUB_API_LATEST = `https://api.github.com/repos/${GITHUB_REPO}/releases/latest`
export const GITHUB_API_TAGS = `https://api.github.com/repos/${GITHUB_REPO}/tags`

export const GITHUB_RELEASE_CACHE_KEY = 'swarm_github_latest_release'
export const GITHUB_RELEASE_TTL_MS = 6 * 60 * 60 * 1000

export interface GithubReleaseHit {
  tag: string
  htmlUrl: string
}

interface CachedHit {
  tag: string
  htmlUrl: string
  checkedAt: number
}

let memoryCache: CachedHit | null = null

function isUsableCache(entry: CachedHit | null, now: number): entry is CachedHit {
  return Boolean(entry && now - entry.checkedAt < GITHUB_RELEASE_TTL_MS)
}

function readSessionCache(now: number): CachedHit | null {
  if (typeof sessionStorage === 'undefined') return null
  try {
    const raw = sessionStorage.getItem(GITHUB_RELEASE_CACHE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as CachedHit
    if (
      typeof parsed?.tag !== 'string' ||
      typeof parsed?.htmlUrl !== 'string' ||
      typeof parsed?.checkedAt !== 'number'
    ) {
      return null
    }
    return isUsableCache(parsed, now) ? parsed : null
  } catch {
    return null
  }
}

function writeCache(hit: CachedHit): void {
  memoryCache = hit
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.setItem(GITHUB_RELEASE_CACHE_KEY, JSON.stringify(hit))
  } catch {
    /* quota / private mode */
  }
}

export function resetGithubReleaseCache(): void {
  memoryCache = null
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.removeItem(GITHUB_RELEASE_CACHE_KEY)
  } catch {
    /* ignore */
  }
}

export function releasePageUrl(tag: string): string {
  const cleaned = tag.trim()
  if (!cleaned) return GITHUB_RELEASES_URL
  return `${GITHUB_RELEASES_URL}/tag/${encodeURIComponent(cleaned)}`
}

function parseLatestPayload(payload: unknown): GithubReleaseHit | null {
  if (!payload || typeof payload !== 'object') return null
  const rec = payload as Record<string, unknown>
  const tag = typeof rec.tag_name === 'string' ? rec.tag_name.trim() : ''
  if (!tag) return null
  const htmlUrl =
    typeof rec.html_url === 'string' && rec.html_url.trim()
      ? rec.html_url.trim()
      : releasePageUrl(tag)
  return { tag, htmlUrl }
}

function parseTagsPayload(payload: unknown): GithubReleaseHit | null {
  if (!Array.isArray(payload) || payload.length === 0) return null
  const first = payload[0]
  if (!first || typeof first !== 'object') return null
  const name = (first as Record<string, unknown>).name
  const tag = typeof name === 'string' ? name.trim() : ''
  if (!tag) return null
  return { tag, htmlUrl: releasePageUrl(tag) }
}

async function fetchJson(url: string): Promise<unknown | null> {
  try {
    const response = await fetch(url, {
      headers: { Accept: 'application/vnd.github+json' },
    })
    if (!response.ok) return null
    return await response.json()
  } catch {
    return null
  }
}

/**
 * Latest public release/tag, or null when GitHub is unreachable / unusable.
 * Cached per session (and up to 6 hours) so we do not hammer the API.
 */
export async function fetchLatestGithubRelease(
  now = Date.now(),
): Promise<GithubReleaseHit | null> {
  if (isUsableCache(memoryCache, now)) {
    return { tag: memoryCache.tag, htmlUrl: memoryCache.htmlUrl }
  }
  const sessionHit = readSessionCache(now)
  if (sessionHit) {
    memoryCache = sessionHit
    return { tag: sessionHit.tag, htmlUrl: sessionHit.htmlUrl }
  }

  const latest = parseLatestPayload(await fetchJson(GITHUB_API_LATEST))
  const hit = latest ?? parseTagsPayload(await fetchJson(GITHUB_API_TAGS))
  if (!hit) return null
  writeCache({ ...hit, checkedAt: now })
  return hit
}
