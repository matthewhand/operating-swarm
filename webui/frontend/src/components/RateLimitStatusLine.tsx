import { openSettingsSheet } from './settings/kernel'
import {
  formatRateLimitWait,
  settingsTargetForProvider,
  type RateLimitWait,
} from '../lib/providerRateLimits'

export default function RateLimitStatusLine({
  wait,
  nowMs = Date.now(),
  ts,
  timeLabel,
}: {
  wait: RateLimitWait
  nowMs?: number
  ts?: string
  timeLabel?: string
}) {
  const target = wait.settings || settingsTargetForProvider(wait.provider)
  const open = () =>
    openSettingsSheet({
      section: target.section,
      providerId: target.provider_id,
      focusRateLimits: true,
    })

  return (
    <p
      className="os-chat-status os-chat-status--rate-limit"
      data-role="status"
      data-testid="chat-status-rate-limit"
      data-provider={wait.provider}
      data-ts={ts}
      role="button"
      tabIndex={0}
      onClick={open}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          open()
        }
      }}
    >
      <span>{formatRateLimitWait(wait, nowMs)}</span>
      {ts && timeLabel ? (
        <time dateTime={ts} data-testid="chat-status-time">
          {timeLabel}
        </time>
      ) : null}
    </p>
  )
}
