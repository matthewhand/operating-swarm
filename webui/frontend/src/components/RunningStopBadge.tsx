/**
 * #1371 — generation status chrome is a "Running" badge with a spinner.
 * The stop/abort control is not standing chrome: it reveals only while the
 * badge is hovered or focused. Click still interrupts the in-flight turn
 * (same `onStop` contract as the retired always-visible Stop button).
 */
import { useCallback, useState, type FocusEvent } from 'react'

export interface RunningStopBadgeProps {
  onStop: () => void
  title?: string
  stopLabel?: string
  /**
   * #1684: the name of the tool call in flight, or `null`/omitted when none
   * is. This is the badge's ONLY signal — `docs/UI_DESIGN.md` §3: eye-dots
   * mean "waiting on a model response", the badge means "a tool call is in
   * flight", and the two must never be driven from one flag. Omitting it
   * renders the stop control with no badge, which is the correct chrome for
   * a plain streaming turn (and for CLI/remote seats, which emit no phase).
   */
  toolName?: string | null
  /**
   * #1684: the OTHER hover target. The avatar's eye-dots are rendered inside
   * the message bubble, not inside this slot, so their hover cannot reach the
   * `.os-running-stop` CSS selector — the owner passes that hover in here.
   *
   * It ORs with this component's own hover/focus state and lands on the SAME
   * `os-running-stop--revealed` class, so `index.css` keeps exactly one reveal
   * rule for two targets instead of a parallel per-target copy
   * (`docs/UI_DESIGN.md`: shared chrome is one shared rule). Omitted → the
   * badge is its own only trigger, which is the pre-#1684 contract.
   */
  revealedExternally?: boolean
}

export function RunningStopBadge({
  onStop,
  title = "Stop this agent's generation (other turns keep running)",
  stopLabel = 'Stop generating',
  toolName = null,
  revealedExternally = false,
}: RunningStopBadgeProps) {
  const [hovered, setHovered] = useState(false)
  const revealed = hovered || revealedExternally

  const reveal = useCallback(() => setHovered(true), [])
  const conceal = useCallback(() => setHovered(false), [])
  const concealIfLeft = useCallback((event: FocusEvent<HTMLSpanElement>) => {
    const next = event.relatedTarget
    if (next instanceof Node && event.currentTarget.contains(next)) return
    setHovered(false)
  }, [])
  const toolLabel = toolName ? `Running · ${toolName}` : 'Running'

  return (
    <span
      className={`os-running-stop${revealed ? ' os-running-stop--revealed' : ''}`}
      data-testid="running-status-badge"
      data-revealed={revealed ? 'true' : 'false'}
      onMouseEnter={reveal}
      onMouseLeave={conceal}
      onPointerEnter={reveal}
      onPointerLeave={conceal}
      onFocus={reveal}
      onBlur={concealIfLeft}
    >
      {/* #1684: the pill is the tool-in-flight mark. It is NOT standing
          chrome — with no tool in flight the slot still hosts the (hover
          revealed) stop control, but shows no badge, so plain streaming can
          never read as "a spinner AND a badge" (one flag, two views). */}
      {toolName ? (
        <span
          className="os-running-stop__badge badge badge-sm badge-info"
          data-status="running"
          data-testid="running-badge-pill"
          data-tool-name={toolName}
        >
          <span className="loading loading-spinner loading-xs" aria-hidden="true" />
          {toolLabel}
        </span>
      ) : null}
      <button
        type="button"
        className="os-agent-row__stop os-running-stop__abort"
        aria-label={stopLabel}
        title={title}
        data-testid="agent-row-stop"
        data-visible={revealed ? 'true' : 'false'}
        onClick={onStop}
      >
        <svg
          viewBox="0 0 16 16"
          className="h-3 w-3 fill-current shrink-0"
          aria-hidden="true"
          focusable="false"
        >
          <rect x="3" y="3" width="10" height="10" rx="1.5" />
        </svg>
        <span className="os-agent-row__stop-label">Stop</span>
      </button>
    </span>
  )
}

export default RunningStopBadge
