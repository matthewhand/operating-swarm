/**
 * Vite/Playwright harness for #1697 visual proof.
 *
 * Unique route: `/__proof__/agent-selector-1697?theme=dark|light`
 *
 * Reproduces the real stacking structure the bug lives in, using the live
 * components: an expanded left rail (`.os-agent-sidebar`, `lg:z-30`) beside a
 * chat column whose `main` is `overflow-hidden`, and the real
 * `ChatBottomDock` chrome — `.os-chat-bottom-dock sticky bottom-0 z-20` →
 * `.os-composer` → `NavbarRoutingPicker` (team seat) → `ModelSearchPalette`.
 *
 * Before the fix the palette's `position: fixed` overlay is trapped in the
 * dock's `z-20` stacking context, so the rail paints over its left edge and
 * the popup reads as `h models` / `ief of Staff`. The in-frame URL bar
 * repeats `window.location.href` so each screenshot carries a distinct path
 * without secrets.
 */
import { useEffect, useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import NavbarRoutingPicker from '../components/NavbarRoutingPicker'
import { isNarrowViewport } from '../lib/narrowViewport'
import { AGENT_SELECTOR_PROOF_1697_PATH } from './proofPaths'

export { AGENT_SELECTOR_PROOF_1697_PATH } from './proofPaths'

export type Proof1697Theme = 'dark' | 'light'

/** Realistic team roster so the palette rows are the long labels from the issue. */
const TEAM_AGENTS = [
  { id: 'all', label: 'All members', kind: 'team' as const },
  { id: 'chief-of-staff', label: 'Chief of Staff', kind: 'team' as const },
  { id: 'engineering-lead', label: 'Engineering Lead', kind: 'team' as const },
  { id: 'product-designer', label: 'Product Designer', kind: 'team' as const },
  { id: 'research-analyst', label: 'Research Analyst', kind: 'team' as const },
  { id: 'release-manager', label: 'Release Manager', kind: 'team' as const },
]

const RAIL_WIDTH = '18rem'

function readTheme(): Proof1697Theme {
  return new URLSearchParams(window.location.search).get('theme') === 'light' ? 'light' : 'dark'
}

function ProofAddressBar({ href }: { href: string }) {
  return (
    <header
      data-testid="proof-chrome-1697"
      className="shrink-0 border-b border-base-300 bg-base-200 px-3 py-2"
    >
      <div className="mb-1 text-xs font-medium text-base-content/70">
        Operating Swarm — Issue #1697 proof
      </div>
      <div
        className="flex items-center gap-2 rounded-box border border-base-300 bg-base-100 px-3 py-1.5"
        data-testid="proof-url-bar-1697"
        aria-label="Proof URL bar"
      >
        <span className="flex gap-1" aria-hidden="true">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-error/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-warning/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-success/70" />
        </span>
        <span className="truncate font-mono text-xs" data-testid="proof-url-1697">
          {href}
        </span>
      </div>
    </header>
  )
}

/**
 * The expanded left sidepane from `AgentSidebar` — same classes, same z-band.
 * Below `lg` the real rail is a drawer that slides off-screen; the harness
 * mirrors that so a narrow capture shows the same geometry the app paints.
 */
function ProofRail({ narrow }: { narrow: boolean }) {
  return (
    <aside
      className={`os-agent-sidebar os-agent-sidebar--left os-agent-sidebar--animated fixed inset-y-0 left-0 z-40 flex shrink-0 flex-col transition-transform duration-200 lg:relative lg:z-30 lg:translate-x-0 ${
        narrow ? '-translate-x-full' : 'translate-x-0'
      }`}
      style={{ width: RAIL_WIDTH }}
      data-testid="os-proof-rail-1697"
      aria-label="Agents"
      data-rail-open={narrow ? 'false' : 'true'}
    >
      <div className="os-rail-search-row flex items-center gap-1.5 px-3 pb-2 pt-3">
        <button type="button" className="os-rail-search min-w-0 flex-1 cursor-pointer">
          <Search className="h-3.5 w-3.5 shrink-0 text-base-content/40" aria-hidden="true" />
          <span className="os-rail-search__input os-rail-search__placeholder">Search</span>
        </button>
      </div>
      <div className="os-rail-scroller min-h-0 flex-1 overflow-y-auto px-2 pb-4">
        <div className="os-rail-section text-[0.7rem] uppercase tracking-wide text-base-content/45 px-2 py-1.5">
          Agents
        </div>
        {['Codey', 'Stewie', 'Ada', 'Skeptic', 'Pat'].map((name) => (
          <div key={name} className="os-agent-row flex items-center gap-2 rounded-lg px-2 py-1.5">
            <span className="inline-block h-6 w-6 shrink-0 rounded-full bg-base-300" aria-hidden="true" />
            <span className="os-agent-row__label-col">
              <span className="os-rail-row-name text-sm text-base-content/80">{name}</span>
            </span>
          </div>
        ))}
      </div>
    </aside>
  )
}

/** The live `ChatBottomDock` chrome: sticky dock → composer row → routing picker. */
function ProofComposer() {
  return (
    <div
      className="os-chat-bottom-dock sticky bottom-0 z-20 -mb-3 border-t border-base-content/5 bg-base-100"
      data-testid="proof-chat-bottom-dock-1697"
    >
      <form className="os-composer-wrap" onSubmit={(event) => event.preventDefault()}>
        <div className="os-composer-row">
          <div className="os-composer">
            <input
              type="text"
              className="os-composer__input"
              placeholder="Message"
              aria-label="Chat message"
              readOnly
            />
            <NavbarRoutingPicker
              seatKind="team"
              aria-label="Team members"
              agents={TEAM_AGENTS}
              allAgents={TEAM_AGENTS}
              selectedAgent="all"
              models={[]}
              selectedModel=""
              placeholder="Team"
              footerAction={{ id: 'manage-teams', label: 'Manage teams', onSelect: () => undefined }}
              onChange={() => undefined}
            />
          </div>
          <button type="button" className="os-composer__icon btn btn-ghost btn-sm btn-circle" aria-label="Send">
            ↑
          </button>
        </div>
      </form>
    </div>
  )
}

export function AgentSelectorProof1697() {
  const theme = useMemo(() => readTheme(), [])
  const narrow = useMemo(() => isNarrowViewport(), [])
  const [href, setHref] = useState(() =>
    typeof window === 'undefined' ? AGENT_SELECTOR_PROOF_1697_PATH : window.location.href,
  )

  useEffect(() => {
    setHref(window.location.href)
    document.documentElement.setAttribute('data-theme', theme)
    document.documentElement.style.colorScheme = theme
    // The proof harness renders the rail without `useRailResize`, so publish the
    // same reserved-width contract the real shell does (#1289 / #1697). The
    // palette overlay is portalled to <body>, so :root is the only shared
    // ancestor it can inherit the inset from. Below the `lg` breakpoint the rail
    // is a drawer and reserves nothing, so the overlay stays full-bleed.
    const root = document.documentElement.style
    if (narrow) {
      root.removeProperty('--os-rail-width')
      root.removeProperty('--os-rail-inset-start')
      root.removeProperty('--os-rail-inset-end')
    } else {
      root.setProperty('--os-rail-width', RAIL_WIDTH)
      root.setProperty('--os-rail-inset-start', RAIL_WIDTH)
      root.setProperty('--os-rail-inset-end', '0px')
    }
    document.title = `Operating Swarm — #1697 ${theme} — ${AGENT_SELECTOR_PROOF_1697_PATH}`
    // Open the composer agent/model selector for path-in-frame captures.
    const t = window.setTimeout(() => {
      document.querySelector<HTMLElement>('[data-testid="routing-face"]')?.click()
    }, 80)
    return () => {
      window.clearTimeout(t)
      root.removeProperty('--os-rail-width')
      root.removeProperty('--os-rail-inset-start')
      root.removeProperty('--os-rail-inset-end')
    }
  }, [narrow, theme])

  const client = useMemo(
    () => new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } }),
    [],
  )

  return (
    <QueryClientProvider client={client}>
      <div
        className="flex h-screen min-h-0 flex-col bg-base-100 text-base-content"
        data-theme={theme}
        data-testid="agent-selector-1697-proof"
        data-proof-theme={theme}
      >
        <ProofAddressBar href={href} />
        {/* Same shell as `App`: rail + chat column in one flex row. */}
        <div className="flex min-h-0 flex-1" data-testid="proof-shell-1697">
          <ProofRail narrow={narrow} />
          <div className="flex min-w-0 flex-1 flex-col">
            <main
              id="os-main"
              className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden"
              tabIndex={-1}
            >
              <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
                <p className="text-sm text-base-content/60" data-testid="proof-caption-1697">
                  Composer agent/model selector open over an 18rem left sidepane — the popup
                  renders fully in the workspace, never under the rail.
                </p>
              </div>
              <ProofComposer />
            </main>
          </div>
        </div>
      </div>
    </QueryClientProvider>
  )
}

export default AgentSelectorProof1697
