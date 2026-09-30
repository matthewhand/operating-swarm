/**
 * Vite/Playwright harness for #1674 visual proof.
 *
 * Unique route: `/__proof__/add-bot-1674?theme=light|dark`
 *
 * Renders the real `.os-rail-search-row` chrome — the Search pill and the `+`
 * — with the real `AddBotMenu` mounted, so the capture shows the dropdown
 * anchored to the control that opens it rather than a re-drawn mock. The
 * in-frame URL bar repeats `window.location.href` so each screenshot carries a
 * distinct path without secrets.
 */
import { useEffect, useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AddBotMenu from '../components/AddBotMenu'
import type { AddBotMenuAgent } from '../components/AddBotMenu'
import { ToastProvider } from '../components/DaisyUI'

export const ADD_BOT_MENU_PROOF_1674_PATH = '/__proof__/add-bot-1674'

const SEED_AGENTS: AddBotMenuAgent[] = [
  { id: 'codey', label: 'Codey' },
  { id: 'stewie', label: 'Stewie' },
  { id: 'ada', label: 'Ada' },
  { id: 'skeptic', label: 'Skeptic' },
  { id: 'cos', label: 'Pat', remoteKind: 'api' },
  { id: 'hermes-bot', label: 'Hermes Bot', remoteKind: 'hermes' },
]

function readTheme(): 'light' | 'dark' {
  return new URLSearchParams(window.location.search).get('theme') === 'dark'
    ? 'dark'
    : 'light'
}

function ProofAddressBar({ href }: { href: string }) {
  return (
    <header
      data-testid="proof-chrome-1674"
      className="border-b border-base-300 bg-base-200 px-3 py-2"
    >
      <div className="mb-1 text-xs font-medium text-base-content/70">
        Operating Swarm · Issue #1674 proof
      </div>
      <div
        className="flex items-center gap-2 rounded-box border border-base-300 bg-base-100 px-3 py-1.5"
        data-testid="proof-url-bar-1674"
        aria-label="Proof URL bar"
      >
        <span className="flex gap-1" aria-hidden="true">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-error/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-warning/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-success/70" />
        </span>
        <span className="truncate font-mono text-xs" data-testid="proof-url-1674">
          {href}
        </span>
      </div>
    </header>
  )
}

/** The rail's "search or create" strip, with the real + menu beside Search. */
function RailSearchRow() {
  return (
    <div className="os-rail-search-row flex items-center gap-1.5 px-3 pb-2 pt-3">
      <button type="button" className="os-rail-search min-w-0 flex-1 cursor-pointer">
        <Search
          className="h-3.5 w-3.5 shrink-0 text-base-content/40"
          aria-hidden="true"
        />
        <span className="os-rail-search__input os-rail-search__placeholder">Search</span>
      </button>
      <AddBotMenu
        triggerLabel="Add agent"
        activeAgentId="codey"
        agents={SEED_AGENTS}
        onCreateBot={() => undefined}
        onCreateGroupChat={() => undefined}
        onStartChat={() => undefined}
      />
    </div>
  )
}

export function AddBotMenuProof1674() {
  const theme = useMemo(() => readTheme(), [])
  const [href, setHref] = useState(() =>
    typeof window === 'undefined' ? ADD_BOT_MENU_PROOF_1674_PATH : window.location.href,
  )

  useEffect(() => {
    setHref(window.location.href)
    document.documentElement.setAttribute('data-theme', theme)
    document.documentElement.style.colorScheme = theme
    document.title = 'Operating Swarm - #1674 add bot - ' + ADD_BOT_MENU_PROOF_1674_PATH
    // Open the menu for path-in-frame captures (and for humans visiting the harness).
    const t = window.setTimeout(() => {
      document.querySelector<HTMLButtonElement>('[data-testid="add-bot-menu-trigger"]')?.click()
    }, 80)
    return () => window.clearTimeout(t)
  }, [theme])

  const client = useMemo(
    () => new QueryClient({ defaultOptions: { queries: { retry: false } } }),
    [],
  )

  return (
    <QueryClientProvider client={client}>
      <ToastProvider>
        <div
          className="min-h-screen bg-base-100 text-base-content"
          data-testid="add-bot-1674-proof"
          data-proof-theme={theme}
        >
          <ProofAddressBar href={href} />
          <p className="px-3 py-2 text-sm" data-testid="proof-caption-1674">
            Add bot menu — Create new agent · Create group chat · your agents. Picking an
            agent starts a new session with it.
          </p>
          <div className="flex items-start" data-testid="proof-rail-1674">
            {/* Rail + empty chat column so the left-anchored 17rem panel + shadow
                stay fully in frame (Skeptic #1674 amendment). */}
            <aside
              className="os-agent-sidebar w-64 shrink-0 border-r border-base-300"
              data-testid="os-proof-rail"
            >
              <RailSearchRow />
            </aside>
            <main
              className="min-h-[28rem] min-w-0 flex-1 bg-base-200/40 px-6 py-4"
              data-testid="proof-chat-1674"
              aria-hidden="true"
            />
          </div>
        </div>
      </ToastProvider>
    </QueryClientProvider>
  )
}

export default AddBotMenuProof1674
