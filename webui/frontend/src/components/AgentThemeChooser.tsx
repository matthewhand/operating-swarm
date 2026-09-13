import {
  useState,
  type HTMLAttributes,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from 'react'
import AgentThemePreviewDialog from './AgentThemePreviewDialog'

export const THEME_CHOOSER_SELECTOR = '[data-theme-chooser]'

export function chooseThemeLabel(name?: string | null): string {
  const trimmed = typeof name === 'string' ? name.trim() : ''
  return trimmed ? `Choose theme for ${trimmed}` : 'Choose theme'
}

export function eventOnThemeChooser(event: { target: EventTarget | null }): boolean {
  const el = event.target
  return el instanceof Element && Boolean(el.closest(THEME_CHOOSER_SELECTOR))
}

export interface AgentThemeChooserProps extends HTMLAttributes<HTMLElement> {
  agentId?: string | null
  name?: string | null
  disabled?: boolean
  children: ReactNode
}

/** Opt-in click-to-assign wrapper (REQ-840). Rail/pins do not use this. */
export default function AgentThemeChooser({
  agentId,
  name,
  disabled,
  children,
  className = '',
  onClick,
  ...rest
}: AgentThemeChooserProps) {
  const [open, setOpen] = useState(false)
  if (!agentId || disabled) return <>{children}</>

  return (
    <>
      <span
        role="button"
        tabIndex={0}
        data-theme-chooser=""
        className={`inline-flex cursor-pointer border-0 bg-transparent p-0 ${className}`.trim()}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={chooseThemeLabel(name || agentId)}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={(event: MouseEvent<HTMLElement>) => {
          event.preventDefault()
          event.stopPropagation()
          onClick?.(event)
          setOpen(true)
        }}
        onKeyDown={(event: KeyboardEvent<HTMLElement>) => {
          if (event.key !== 'Enter' && event.key !== ' ') return
          event.preventDefault()
          event.stopPropagation()
          setOpen(true)
        }}
        {...rest}
      >
        {children}
      </span>
      {open ? (
        <AgentThemePreviewDialog
          agentId={agentId}
          isOpen={open}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </>
  )
}
