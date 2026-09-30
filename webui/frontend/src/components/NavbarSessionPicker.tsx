/**
 * #1202 — the navbar `[ 💬 Session ]` control.
 *
 * A capability-aware shell around the existing CLI / API / Remote session
 * switchers (reused verbatim as `children`). When the active seat advertises
 * `sessions` it renders the real switcher; when it does not, the control stays
 * **mounted but greyed** (`opacity: .4`, `cursor: not-allowed`), the switcher
 * is not mounted, and the click is inert — with a capability-aware tooltip.
 *
 * It neither switches the active seat nor rewrites `blueprint_id`; the
 * switchers own their own session navigation.
 */
import type { ReactNode } from 'react'
import { History } from 'lucide-react'

export interface NavbarSessionPickerProps {
  /** True when the seat cannot support persistent sessions. */
  disabled?: boolean
  /** Capability-aware tooltip shown when disabled. */
  reason?: string
  label?: string
  /**
   * #1353 — the provider scope the child switcher lists sessions for
   * (`cli:opencode`, `remote:hermes`, …). Surfaced as a scope marker so the
   * selected provider — never the default inference profile — governs the
   * list. The child switcher owns the actual session fetch.
   */
  provider?: string
  children?: ReactNode
}

export const NAVBAR_SESSION_PICKER_TESTID = 'os-navbar-session-picker'
export const NAVBAR_SESSION_SCOPE_TESTID = 'os-navbar-session-scope'

export function NavbarSessionPicker({
  disabled = false,
  reason = '',
  label = 'Select session',
  provider = '',
  children,
}: NavbarSessionPickerProps) {
  const scope = provider.trim()
  if (!disabled) {
    if (!scope) return <>{children}</>
    return (
      <span
        style={{ display: 'contents' }}
        data-testid={NAVBAR_SESSION_SCOPE_TESTID}
        data-provider={scope}
      >
        {children}
      </span>
    )
  }

  const tip = reason || label
  return (
    <span
      className="tooltip tooltip-bottom os-navbar-picker os-navbar-picker--disabled"
      data-tip={tip}
      data-disabled="true"
      title={tip}
    >
      <button
        type="button"
        className="btn btn-ghost btn-sm btn-square opacity-40 cursor-not-allowed"
        disabled
        aria-disabled="true"
        aria-label={tip}
        title={tip}
        data-tip={tip}
        data-testid={NAVBAR_SESSION_PICKER_TESTID}
        data-disabled="true"
        data-provider={scope || undefined}
      >
        <History className="h-4 w-4" aria-hidden="true" />
      </button>
    </span>
  )
}

export default NavbarSessionPicker
