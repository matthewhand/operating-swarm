import { useEffect, useRef, useState } from 'react'
import { LifeBuoy } from 'lucide-react'
import { renderSafeMarkdown } from '../lib/markdown'
import { handleSettingsLinkClick, SPA_SETTINGS_INFERENCE_HREF } from '../lib/settingsLinks'

/**
 * One-way System → Support chip. Same family as planned “Message from
 * &lt;avatars&gt; &lt;names&gt;” handoff pills. Not a chat bubble — Support
 * cannot reply to it. Click expands compressed config intel.
 */
export function SupportBriefingPill({ briefing }: { briefing: string }) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    const onPointer = (event: MouseEvent) => {
      const root = rootRef.current
      if (root && !root.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onPointer)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onPointer)
    }
  }, [open])

  return (
    <div className="os-handoff-chip-wrap" ref={rootRef}>
      <button
        type="button"
        className="os-handoff-chip os-handoff-chip--system"
        aria-expanded={open}
        aria-controls="os-support-briefing"
        aria-haspopup="true"
        onClick={() => setOpen((value) => !value)}
      >
        <span className="os-handoff-avatars" aria-hidden="true">
          <span className="os-handoff-avatar os-handoff-avatar--system">S</span>
          <span className="os-handoff-avatar os-handoff-avatar--support">
            <LifeBuoy className="h-3 w-3" />
          </span>
        </span>
        <span className="os-handoff-label">System → Support</span>
        <span className="sr-only">. One-way briefing. Support cannot reply.</span>
      </button>
      {open ? (
        <div
          id="os-support-briefing"
          className="os-briefing-popover"
          role="region"
          aria-label="Support briefing"
        >
          {briefing ? (
            <div
              data-testid="support-briefing"
              className="os-briefing-md chat-md break-words [&_p]:my-1 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_ul]:my-1 [&_ul]:list-disc [&_ul]:pl-5 [&_strong]:font-semibold"
              dangerouslySetInnerHTML={{ __html: renderSafeMarkdown(briefing) }}
              onClick={(event) => {
                handleSettingsLinkClick(event.nativeEvent)
              }}
            />
          ) : (
            <p className="text-sm opacity-60">—</p>
          )}
        </div>
      ) : null}
    </div>
  )
}

export const SUPPORT_ACTION_CHIPS = [
  { label: 'New rig', href: '/teams/launch/' },
  { label: 'Set inference', href: SPA_SETTINGS_INFERENCE_HREF },
  { label: 'Write blueprint', href: '/agent-creator/' },
] as const

export function SupportActionChips() {
  return (
    <nav className="os-support-chips" aria-label="Support shortcuts">
      {SUPPORT_ACTION_CHIPS.map((chip) => (
        <a
          key={chip.href}
          href={chip.href}
          className="os-handoff-chip os-handoff-chip--action"
          onClick={(event) => {
            handleSettingsLinkClick(event.nativeEvent)
          }}
        >
          {chip.label}
        </a>
      ))}
    </nav>
  )
}
