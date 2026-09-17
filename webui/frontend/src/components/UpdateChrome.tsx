import { useCallback, useEffect, useMemo, useState } from 'react'
import { Cloud, Info } from 'lucide-react'
import {
  GITHUB_ISSUES_URL,
  fetchLatestGithubRelease,
  releasePageUrl,
  type GithubReleaseHit,
} from '../lib/githubRelease'
import { SPA_HELLO_EVENT, getExpectedSpaVersion } from '../lib/spaHello'
import { getBakedSpaVersion } from '../lib/spaVersion'
import { resolveUpdateChrome, type UpdateChromeKind } from '../lib/spaUpdate'

const ISSUES_LABEL = 'Operating Swarm issues'
const LOCAL_LABEL = 'Reload to update this tab'
const UPSTREAM_LABEL = 'Newer Operating Swarm release available'

const LOCAL_TOOLTIP =
  'This tab’s SPA is behind the connected backend. Reload to fetch the new UI.'
const LOCAL_AND_UPSTREAM_TOOLTIP =
  'This tab’s SPA is behind the connected backend. Reload to fetch the new UI. A newer GitHub release is also available.'
const UPSTREAM_TOOLTIP =
  'A newer Operating Swarm release is on GitHub. Opens that release page.'
const IDLE_TOOLTIP = 'Operating Swarm issues on GitHub'

export function updateChromeAriaLabel(kind: UpdateChromeKind): string {
  if (kind === 'local') return LOCAL_LABEL
  if (kind === 'upstream') return UPSTREAM_LABEL
  return ISSUES_LABEL
}

/** #547: the short on-screen form of the label. `idle` is not an alarm, so the
 *  glyph alone carries it; the other two say what they mean when the rail is
 *  wide enough. Revealed by a container query, hidden under the threshold. */
export function updateChromeVisibleLabel(kind: UpdateChromeKind): string | null {
  if (kind === 'local') return 'Reload'
  if (kind === 'upstream') return 'Update available'
  return null
}

export function updateChromeTooltip(
  kind: UpdateChromeKind,
  alsoUpstream: boolean,
): string {
  if (kind === 'local') {
    return alsoUpstream ? LOCAL_AND_UPSTREAM_TOOLTIP : LOCAL_TOOLTIP
  }
  if (kind === 'upstream') return UPSTREAM_TOOLTIP
  return IDLE_TOOLTIP
}

export default function UpdateChrome({
  reload = () => window.location.reload(),
  openUrl = (url: string) => {
    window.open(url, '_blank', 'noopener,noreferrer')
  },
}: {
  reload?: () => void
  openUrl?: (url: string) => void
}) {
  const bakedVersion = getBakedSpaVersion()
  const [backendVersion, setBackendVersion] = useState<string | null>(
    () => getExpectedSpaVersion(),
  )
  const [github, setGithub] = useState<GithubReleaseHit | null>(null)

  useEffect(() => {
    const onHello = (event: Event) => {
      const detail = (event as CustomEvent<string | null>).detail
      setBackendVersion(typeof detail === 'string' && detail.trim() ? detail : null)
    }
    window.addEventListener(SPA_HELLO_EVENT, onHello)
    return () => window.removeEventListener(SPA_HELLO_EVENT, onHello)
  }, [])

  useEffect(() => {
    let cancelled = false
    void fetchLatestGithubRelease().then((hit) => {
      if (!cancelled) setGithub(hit)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const resolved = useMemo(
    () =>
      resolveUpdateChrome({
        bakedVersion,
        backendVersion,
        githubLatest: github?.tag ?? null,
      }),
    [bakedVersion, backendVersion, github],
  )

  const onClick = useCallback(() => {
    if (resolved.kind === 'local') {
      reload()
      return
    }
    if (resolved.kind === 'upstream') {
      openUrl(github?.htmlUrl || releasePageUrl(github?.tag ?? ''))
      return
    }
    openUrl(GITHUB_ISSUES_URL)
  }, [github, openUrl, reload, resolved.kind])

  const label = updateChromeAriaLabel(resolved.kind)
  const tip = updateChromeTooltip(resolved.kind, resolved.alsoUpstream)
  const visibleLabel = updateChromeVisibleLabel(resolved.kind)
  const Icon = resolved.kind === 'idle' ? Info : Cloud

  return (
    <button
      type="button"
      className={`os-rail-update-chrome os-rail-update-chrome--${resolved.kind} btn btn-ghost btn-xs btn-square h-5 w-5 min-h-0`}
      data-testid="rail-update-chrome"
      data-kind={resolved.kind}
      data-also-upstream={resolved.alsoUpstream ? 'true' : 'false'}
      aria-label={label}
      title={tip}
      onClick={onClick}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      {visibleLabel ? (
        <span className="os-rail-update-chrome__label" aria-hidden="true">
          {visibleLabel}
        </span>
      ) : null}
    </button>
  )
}
