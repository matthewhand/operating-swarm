import { Badge, Button } from './DaisyUI'
import type { ToolCallState, ToolCallStatus } from '../lib/safety'

export type ToolDecision = 'allow' | 'always' | 'deny'

const STATUS_LABEL: Record<ToolCallStatus, string> = {
  running: 'Running',
  allowed: 'Allowed',
  done: 'Done',
  denied: 'Denied',
  error: 'Error',
}

function badgeType(status: ToolCallStatus): 'info' | 'success' | 'error' {
  if (status === 'running') return 'info'
  if (status === 'denied' || status === 'error') return 'error'
  return 'success'
}

export function ToolStatusBadge({ status }: { status: ToolCallStatus }) {
  const running = status === 'running'
  return (
    <Badge
      type={badgeType(status)}
      size="sm"
      className={running ? 'os-tool-badge-running' : undefined}
    >
      <span data-testid="tool-status-badge" data-status={status}>
        {STATUS_LABEL[status]}
      </span>
    </Badge>
  )
}

export interface ToolCallPopupProps {
  tool: ToolCallState
  onDecision?: (decision: ToolDecision) => void
  /**
   * #1764: when the under-message RunningStopBadge already names this call
   * (`Running · <tool>`), hide the in-bubble status badge so one tool never
   * paints two identical Running pills. Omitted / false keeps the badge
   * (late frames, seats with no tool_phase, GenerationsPanel).
   */
  hideRunningBadge?: boolean
}

/** Assistant-message tool popup: coloured badge + Safety approval card. */
export function ToolCallPopup({ tool, onDecision, hideRunningBadge = false }: ToolCallPopupProps) {
  const showStatusBadge = !(hideRunningBadge && tool.status === 'running')
  return (
    <div className="os-tool-popup mt-2" data-tool-name={tool.name} data-tool-status={tool.status}>
      <div className="flex items-center gap-2">
        <span className="font-mono text-xs">{tool.name}</span>
        {showStatusBadge ? <ToolStatusBadge status={tool.status} /> : null}
      </div>
      {tool.needsApproval ? (
        <div
          className="os-safety-approval mt-2 rounded-box border border-base-300 bg-base-100 p-3"
          role="dialog"
          aria-label="Safety approval"
        >
          <p className="text-sm">
            Safety is concerned about <span className="font-mono">{tool.name}</span>.
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              color="success"
              onClick={() => onDecision?.('allow')}
            >
              Allow once
            </Button>
            <Button
              type="button"
              size="sm"
              color="info"
              onClick={() => onDecision?.('always')}
            >
              Always allow
            </Button>
            <Button
              type="button"
              size="sm"
              color="error"
              onClick={() => onDecision?.('deny')}
            >
              Deny
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

export default ToolCallPopup
