import type { ReactElement } from 'react'
import FocusTrap from 'focus-trap-react'

export interface OverlayFocusTrapProps {
  children: ReactElement
  onClose?: () => void
  initialFocus?: () => HTMLElement | SVGElement | null
}

/**
 * Tab trap for fixed overlays that are not native <dialog>.showModal().
 * Settings / DaisyUI Modal keep the UA trap instead (#313).
 */
export function OverlayFocusTrap({
  children,
  onClose,
  initialFocus,
}: OverlayFocusTrapProps) {
  return (
    <FocusTrap
      focusTrapOptions={{
        allowOutsideClick: true,
        clickOutsideDeactivates: false,
        escapeDeactivates: Boolean(onClose),
        onDeactivate: onClose,
        initialFocus: initialFocus
          ? () => initialFocus() || false
          : undefined,
        fallbackFocus: () => document.body,
        returnFocusOnDeactivate: true,
      }}
    >
      {children}
    </FocusTrap>
  )
}
