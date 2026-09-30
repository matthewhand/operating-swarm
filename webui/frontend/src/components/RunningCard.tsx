import { ArrowUpRight } from 'lucide-react'
import {
  RUNNING_CARD_STOP_CLASS,
  type FanOutLegStatus,
} from '../lib/runningCards'

export interface RunningCardProps {
  legId: string
  name: string
  badge: string
  status: FanOutLegStatus
  live?: boolean
  href?: string
  external?: boolean
  onStop?: (legId: string) => void
}

/**
 * #1374 — one stacked fan-out row.
 *
 * Title on the left, a status badge, and a diagonal open arrow on the
 * right. Stop is mounted only while the leg is Running, and it stays
 * concealed until the pointer or keyboard focus is on that badge.
 */
export function RunningCard({
  legId,
  name,
  badge,
  status,
  live = false,
  href,
  external = false,
  onStop,
}: RunningCardProps) {
  const showStop = live && typeof onStop === 'function'
  return (
    <article
      className="os-running-card"
      data-testid="running-card"
      data-leg-id={legId}
      data-status={status}
      aria-label={`${name} ${badge}`}
    >
      <div className="os-running-card__body min-w-0">
        <p className="os-running-card__name truncate" data-testid="running-card-name">
          {name}
        </p>
      </div>
      <div className="os-running-card__actions">
        <span
          className={`badge badge-sm os-running-card__badge group/badge ${
            status === 'running'
              ? 'badge-info'
              : status === 'done'
                ? 'badge-success'
                : status === 'error'
                  ? 'badge-error'
                  : 'badge-ghost'
          }`}
          data-testid="running-card-status"
          data-status={status}
        >
          <span>{badge}</span>
          {live ? (
            <span
              className="loading loading-spinner loading-xs"
              data-testid="running-card-spinner"
              aria-hidden="true"
            />
          ) : null}
          {showStop ? (
            <button
              type="button"
              className={RUNNING_CARD_STOP_CLASS}
              aria-label={`Stop ${name}`}
              title="Stop this agent (other agents keep running)"
              data-testid="running-card-stop"
              onClick={(event) => {
                event.preventDefault()
                event.stopPropagation()
                onStop?.(legId)
              }}
            >
              <span className="os-running-card__stop-label">Stop</span>
            </button>
          ) : null}
        </span>
        {href ? (
          <a
            className="os-running-card__open"
            href={href}
            target={external ? '_blank' : undefined}
            rel={external ? 'noopener noreferrer' : undefined}
            data-testid="running-card-open"
            aria-label={`Open ${name}`}
            title={`Open ${name}`}
          >
            <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
          </a>
        ) : null}
      </div>
    </article>
  )
}

export default RunningCard
