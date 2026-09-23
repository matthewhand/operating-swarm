import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Bot,
  Book,
  History,
  MessageSquare,
  Moon,
  PlusCircle,
  Search,
  Settings,
  Users,
} from 'lucide-react'
import { OverlayFocusTrap } from '../components/OverlayFocusTrap'

/**
 * EXPERIMENTAL: ⌘K / Ctrl+K command palette.
 *
 * Fuzzy-jumps between the SPA routes and the Django operator pages, plus
 * quick actions (theme flip). Toggle off with:
 *   localStorage.setItem('swarm_experimental_command_palette', 'off')
 */

interface PaletteItem {
  id: string
  label: string
  hint?: string
  icon: React.ReactNode
  /** SPA route (react-router navigate) or full-page Django path. */
  to?: string
  action?: () => void
}

/** Subsequence match with contiguity/prefix bonuses; -1 means no match. */
function fuzzyScore(query: string, target: string): number {
  const q = query.toLowerCase()
  const t = target.toLowerCase()
  if (!q) return 1
  let score = 0
  let ti = 0
  let streak = 0
  for (let qi = 0; qi < q.length; qi += 1) {
    const idx = t.indexOf(q[qi], ti)
    if (idx === -1) return -1
    streak = idx === ti ? streak + 1 : 1
    score += 10 * streak + (idx === 0 ? 5 : 0)
    ti = idx + 1
  }
  return score
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [activeIdx, setActiveIdx] = useState(0)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const listRef = useRef<HTMLUListElement | null>(null)
  const navigate = useNavigate()

  // Theme flip is delegated to App via a window event so the toggle button,
  // persisted value, and palette never disagree.
  const flipTheme = useCallback(() => {
    window.dispatchEvent(new CustomEvent('swarm:toggle-theme'))
  }, [])

  const items: PaletteItem[] = useMemo(
    () => [
      { id: 'home', label: 'Start', hint: 'Landing', icon: <Bot className="h-4 w-4" />, to: '/' },
      { id: 'chat', label: 'Chat', hint: 'Live websocket chat', icon: <MessageSquare className="h-4 w-4" />, to: '/chat' },
      { id: 'blueprints', label: 'Blueprints', hint: '/blueprint-library/', icon: <Book className="h-4 w-4" />, to: '/blueprint-library/' },
      { id: 'my-blueprints', label: 'My Blueprints', hint: '/blueprint-library/my-blueprints/', icon: <Book className="h-4 w-4" />, to: '/blueprint-library/my-blueprints/' },
      { id: 'launch', label: 'Launch a Team', hint: '/teams/launch/', icon: <PlusCircle className="h-4 w-4" />, to: '/teams/launch/' },
      { id: 'teams', label: 'Manage Teams', hint: '/teams/', icon: <Users className="h-4 w-4" />, to: '/teams/' },
      {
        id: 'compose',
        label: 'Compose team roster',
        hint: 'Drag-drop overlay (team_rosters.json)',
        icon: <PlusCircle className="h-4 w-4" />,
        action: () => window.dispatchEvent(new CustomEvent('swarm:open-team-composer')),
      },
      { id: 'sessions', label: 'Sessions', hint: 'Session explorer', icon: <History className="h-4 w-4" />, to: '/sessions/' },
      {
        id: 'settings',
        label: 'Settings',
        hint: 'Chat settings sheet',
        icon: <Settings className="h-4 w-4" />,
        action: () => {
          window.dispatchEvent(new CustomEvent('swarm:open-settings'))
        },
      },
      {
        id: 'theme',
        label: 'Toggle light/dark theme',
        hint: 'Appearance',
        icon: <Moon className="h-4 w-4" />,
        action: flipTheme,
      },
    ],
    [flipTheme],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen((prev) => !prev)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (open) {
      setQuery('')
      setActiveIdx(0)
      // Focus after paint so the dialog exists in jsdom/e2e queries.
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [open])

  const results = useMemo(() => {
    const scored = items
      .map((item) => ({ item, score: fuzzyScore(query, `${item.label} ${item.hint ?? ''}`) }))
      .filter((r) => r.score >= 0)
    scored.sort((a, b) => b.score - a.score)
    return scored.map((r) => r.item)
  }, [items, query])

  useEffect(() => {
    setActiveIdx(0)
  }, [query])

  const choose = useCallback(
    (item: PaletteItem | undefined) => {
      if (!item) return
      setOpen(false)
      if (item.action) item.action()
      else if (item.to) {
        if (item.to.startsWith('/chat')) navigate(item.to)
        else window.location.assign(item.to)
      }
    },
    [navigate],
  )

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      setOpen(false)
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx((i) => Math.min(i + 1, results.length - 1))
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx((i) => Math.max(i - 1, 0))
      return
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      choose(results[activeIdx])
    }
  }

  if (!open) return null

  return (
    <OverlayFocusTrap onClose={() => setOpen(false)} initialFocus={() => inputRef.current}>
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center bg-black/40 pt-[12vh]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) setOpen(false)
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="w-full max-w-lg rounded-box border border-base-300 bg-base-100 shadow-2xl"
      >
        <div className="flex items-center gap-2 border-b border-base-300 px-4 py-3">
          <Search className="h-4 w-4 opacity-60" aria-hidden="true" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Jump to… (⌘K)"
            aria-label="Search commands"
            aria-controls="command-palette-list"
            aria-activedescendant={
              results[activeIdx] ? `cmd-${results[activeIdx].id}` : undefined
            }
            role="combobox"
            aria-expanded="true"
            className="w-full bg-transparent outline-none"
          />
          <kbd className="kbd kbd-sm">esc</kbd>
        </div>
        <ul
          id="command-palette-list"
          ref={listRef}
          role="listbox"
          aria-label="Commands"
          className="max-h-80 overflow-y-auto p-2"
        >
          {results.length === 0 && (
            <li className="px-3 py-6 text-center text-sm opacity-60">
              No matching commands
            </li>
          )}
          {results.map((item, idx) => (
            <li
              key={item.id}
              id={`cmd-${item.id}`}
              role="option"
              aria-selected={idx === activeIdx}
              className={`flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm ${
                idx === activeIdx ? 'bg-base-200' : ''
              }`}
              onMouseMove={() => setActiveIdx(idx)}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(item)}
            >
              <span className="opacity-70">{item.icon}</span>
              <span className="flex-1">{item.label}</span>
              {item.hint && (
                <span className="text-xs opacity-50">{item.hint}</span>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
    </OverlayFocusTrap>
  )
}
