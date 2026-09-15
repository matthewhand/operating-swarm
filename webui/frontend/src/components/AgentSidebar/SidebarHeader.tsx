import { useState, useRef, useEffect, memo } from 'react'
import {
  SlidersHorizontal,
  PanelLeftClose,
  PanelLeft,
  Check,
  LayoutGrid,
  AlignJustify,
  Rows3,
  Palette,
} from 'lucide-react'
import type { SidebarDensity } from '../../types/agent'
import { AVATAR_THEMES, AVATAR_EYES } from '../../types/agent'
import { useAgentStore } from '../../lib/agent-store'
import { SidebarConcealButton } from '../SidepaneConceal'

interface SidebarHeaderProps {
  density: SidebarDensity
  isOpen: boolean
  onToggleOpen: () => void
  onSelectDensity: (density: SidebarDensity) => void
}

const DENSITY_OPTIONS: { id: SidebarDensity; label: string; hint: string }[] = [
  { id: 'icons', label: 'Icons Only', hint: '80px' },
  { id: 'compact', label: 'Compact', hint: '272px' },
  { id: 'comfortable', label: 'Comfortable', hint: '320px' },
]

export const SidebarHeader = memo(function SidebarHeader({
  density,
  isOpen,
  onToggleOpen,
  onSelectDensity
}: SidebarHeaderProps) {
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const avatarTheme = useAgentStore((s) => s.avatarTheme)
  const setAvatarTheme = useAgentStore((s) => s.setAvatarTheme)
  const avatarEyes = useAgentStore((s) => s.avatarEyes)
  const setAvatarEyes = useAgentStore((s) => s.setAvatarEyes)
  const cycleAvatarTheme = () => {
    const i = AVATAR_THEMES.findIndex((t) => t.id === avatarTheme)
    const next = AVATAR_THEMES[(i + 1) % AVATAR_THEMES.length]
    setAvatarTheme(next.id)
  }

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    window.addEventListener('mousedown', handleClickOutside)
    return () => window.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Icons rail must keep density controls; hiding them trapped users in 80px.
  if (density === 'icons') {
    return (
      <div className="flex flex-col items-center py-2 border-b border-base-300/60 gap-1">
        <button
          type="button"
          onClick={() => onSelectDensity('icons')}
          className="btn btn-ghost btn-xs btn-circle text-primary"
          title="Icons only (current)"
          aria-label="Icons only layout"
          aria-pressed="true"
        >
          <LayoutGrid className="w-3.5 h-3.5" />
        </button>
        <button
          type="button"
          onClick={() => onSelectDensity('compact')}
          className="btn btn-ghost btn-xs btn-circle text-base-content/70 hover:text-base-content"
          title="Compact (272px)"
          aria-label="Compact layout"
        >
          <AlignJustify className="w-3.5 h-3.5" />
        </button>
        <button
          type="button"
          onClick={() => onSelectDensity('comfortable')}
          className="btn btn-ghost btn-xs btn-circle text-base-content/70 hover:text-base-content"
          title="Comfortable (320px)"
          aria-label="Comfortable layout"
        >
          <Rows3 className="w-3.5 h-3.5" />
        </button>
        <button
          type="button"
          onClick={cycleAvatarTheme}
          className="btn btn-ghost btn-xs btn-circle text-base-content/70 hover:text-base-content"
          title={`Avatar pack: ${avatarTheme}`}
          aria-label="Cycle avatar pack"
        >
          <Palette className="w-3.5 h-3.5" />
        </button>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-between gap-2 px-2 py-1.5 border-b border-base-300/60">
      {isOpen ? <SidebarConcealButton onClick={onToggleOpen} /> : <span />}
      <div className="flex items-center gap-1">
        {/* Density Dropdown */}
        <div className="relative" ref={dropdownRef}>
          <button
            type="button"
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="btn btn-ghost btn-xs btn-circle text-base-content/70 hover:text-base-content"
            title="Sidebar Density"
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
          </button>

          {dropdownOpen && (
            <div className="absolute right-0 top-full mt-1.5 z-50 w-52 bg-base-100 border border-base-300 rounded-xl shadow-xl p-1.5 text-xs text-base-content backdrop-blur-md animate-in fade-in zoom-in-95 duration-100">
              <div className="px-2 py-1 font-semibold text-base-content/50 uppercase tracking-wider text-[10px]">
                Sidebar Layout
              </div>
              {DENSITY_OPTIONS.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => {
                    onSelectDensity(opt.id)
                    setDropdownOpen(false)
                  }}
                  className="w-full flex items-center justify-between px-2 py-1.5 rounded-lg hover:bg-base-200 text-left"
                >
                  <span>{opt.label} ({opt.hint})</span>
                  {density === opt.id && <Check className="w-3.5 h-3.5 text-primary" />}
                </button>
              ))}
              <div className="px-2 pt-2 pb-1 font-semibold text-base-content/50 uppercase tracking-wider text-[10px]">
                Avatar pack
              </div>
              {AVATAR_THEMES.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => {
                    setAvatarTheme(opt.id)
                    setDropdownOpen(false)
                  }}
                  className="w-full flex items-center justify-between px-2 py-1.5 rounded-lg hover:bg-base-200 text-left"
                >
                  <span>{opt.label} <span className="text-base-content/50">({opt.hint})</span></span>
                  {avatarTheme === opt.id && <Check className="w-3.5 h-3.5 text-primary" />}
                </button>
              ))}
              <div className="px-2 pt-2 pb-1 font-semibold text-base-content/50 uppercase tracking-wider text-[10px]">
                Eyes
              </div>
              {AVATAR_EYES.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => {
                    setAvatarEyes(opt.id)
                    setDropdownOpen(false)
                  }}
                  className="w-full flex items-center justify-between px-2 py-1.5 rounded-lg hover:bg-base-200 text-left"
                >
                  <span>{opt.label} <span className="text-base-content/50">({opt.hint})</span></span>
                  {avatarEyes === opt.id && <Check className="w-3.5 h-3.5 text-primary" />}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Collapse Sidebar Button */}
        <button
          type="button"
          onClick={onToggleOpen}
          className="btn btn-ghost btn-xs btn-circle text-base-content/70 hover:text-base-content"
          title="Toggle sidebar (Ctrl+B)"
        >
          {isOpen ? (
            <PanelLeftClose className="w-3.5 h-3.5" />
          ) : (
            <PanelLeft className="w-3.5 h-3.5" />
          )}
        </button>
      </div>
    </div>
  )
})
