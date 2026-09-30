/**
 * Vite/Playwright harness for #1447 visual proof.
 *
 * Unique route: `/__proof__/ia-1447?surface=computer|config`
 * In-frame URL chrome repeats `window.location.href` so each screenshot
 * carries a distinct path without secrets.
 *
 * The navbar is the live `ChatHeader` ChatPage mounts (avatar, pencil,
 * computer-control, theme, settings). Config opens from that avatar.
 * Pencil and right-click still request the full agent editor. The route
 * stays off production builds unless `VITE_IA_1447_PROOF=1`.
 */
import { useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { Folder, PanelLeft, Pencil, Settings } from 'lucide-react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AgentAvatar from '../components/AgentAvatar'
import { AuxActivityIndicator } from '../components/AuxActivityIndicator'
import { ComputerControlStub } from '../components/ComputerControlStub'
import GroupAvatar from '../components/GroupAvatar'
import { OPEN_SETTINGS_EVENT } from '../components/settings/kernel'
import ThemeToggle from '../components/ThemeToggle'
import { ChatHeader } from '../features/chat/ChatHeader'
import { roleCssClass } from '../lib/agentRoles'
import { openChromeOverlay } from '../lib/chromeOverlay'
import { IA_1447_PROOF_PATH } from './proofPaths'

export { IA_1447_PROOF_PATH, isIa1447ProofEnabled } from './proofPaths'

export type Proof1447Surface = 'computer' | 'config'

function readSurface(): Proof1447Surface {
  const params = new URLSearchParams(window.location.search)
  return params.get('surface') === 'config' ? 'config' : 'computer'
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

type ProofFetchWindow = Window & {
  __proof1447Fetch?: boolean
  __proof1447Restore?: () => void
}

/**
 * Stub the handful of reads the proof surfaces make.
 * Returns a disposer. The wrapper must not outlive the harness: after a
 * visit to `/__proof__/ia-1447`, client-side navigation back to chat would
 * otherwise keep serving empty routines, skills, and sandbox payloads.
 *
 * A second call while the stub is active returns the same disposer.
 * StrictMode renders twice and drops the first render's hooks, so handing
 * back a no-op would leave `window.fetch` patched after unmount.
 */
function installProofFetch(): () => void {
  const marked = window as ProofFetchWindow
  if (marked.__proof1447Restore) return marked.__proof1447Restore
  const original = window.fetch
  const callOriginal = original.bind(window)
  const wrapped = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/test-schedules/status')) {
      return jsonResponse({ object: 'test_schedule_status', failure_count: 0, failures: [] })
    }
    if (url.includes('/test-schedules')) {
      return jsonResponse({ object: 'test_schedule_list', schedules: [], failure_count: 0 })
    }
    if (url.includes('/routines')) {
      return jsonResponse({ object: 'routine_list', agent_id: 'codey', routines: [] })
    }
    if (url.includes('/sandbox-display')) {
      return jsonResponse({ provider: 'none', display: null, reason: 'provider_not_daytona', available: false })
    }
    if (url.includes('/llm-profiles')) {
      return jsonResponse({
        object: 'llm_profiles',
        profiles: [{ id: 'profile-1', name: 'Profile One', model: 'gpt-x' }],
        default_llm_profile: '',
        warnings: [],
      })
    }
    if (url.includes('/skills') || url.endsWith('/v1/skills/')) {
      return jsonResponse({ data: [] })
    }
    return callOriginal(input, init)
  }) as typeof fetch
  const restore = () => {
    if (window.fetch === wrapped) window.fetch = original
    if (marked.__proof1447Restore === restore) {
      delete marked.__proof1447Fetch
      delete marked.__proof1447Restore
    }
  }
  marked.__proof1447Fetch = true
  marked.__proof1447Restore = restore
  window.fetch = wrapped
  return restore
}

function ProofAddressBar({ href }: { href: string }) {
  return (
    <header
      data-testid="proof-chrome-1447"
      className="border-b border-base-300 bg-base-200 px-3 py-2"
    >
      <div className="mb-1 text-xs font-medium text-base-content/70">
        Operating Swarm · Issue #1447 proof
      </div>
      <div
        className="flex items-center gap-2 rounded-box border border-base-300 bg-base-100 px-3 py-1.5"
        data-testid="proof-url-bar-1447"
        aria-label="Proof URL bar"
      >
        <span className="flex gap-1" aria-hidden="true">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-error/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-warning/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-success/70" />
        </span>
        <span className="truncate font-mono text-xs" data-testid="proof-url-1447">
          {href}
        </span>
      </div>
    </header>
  )
}

function LiveChatHeader({ surface }: { surface: Proof1447Surface }) {
  const [editorAgentId, setEditorAgentId] = useState<string | null>(null)
  const [generationsOpened, setGenerationsOpened] = useState(false)

  useEffect(() => {
    if (surface === 'computer') {
      openChromeOverlay('computer-control')
      return
    }
    document
      .querySelector<HTMLButtonElement>('[data-testid="header-avatar-generations"]')
      ?.click()
  }, [surface])

  return (
    <div data-testid={surface === 'computer' ? 'proof-1447-computer' : 'proof-1447-config'}>
      <ChatHeader
        AgentAvatar={AgentAvatar}
        GroupAvatar={GroupAvatar}
        AuxActivityIndicator={AuxActivityIndicator}
        ComputerControlStub={ComputerControlStub}
        ThemeToggle={ThemeToggle}
        Settings={Settings}
        Pencil={Pencil}
        Folder={Folder}
        PanelLeft={PanelLeft}
        OPEN_SETTINGS_EVENT={OPEN_SETTINGS_EVENT}
        roleCssClass={roleCssClass}
        activeChatAgentId="codey"
        headerFaceAgentId="codey"
        selectedBlueprint="codey"
        selectedAgentName="Codey"
        selectedAgent={{
          id: 'codey',
          name: 'Codey',
          kind: 'api',
          instructions: 'You are Codey.',
          provider: 'openai',
          model: 'gpt-x',
        }}
        agentKind="api"
        showHeaderRole
        headerRole="engineer"
        headerRoleLabel="Engineer"
        allPaletteAgents={[{ id: 'codey', label: 'Codey', kind: 'api', provider: 'api' }]}
        navbarCapabilities={{
          agents: { enabled: true, reason: '' },
          sessions: { enabled: false, reason: 'Proof seat has no session backend' },
        }}
        hideUnsupportedSessionPicker
        auxTasks={[]}
        requestAuxCancel={() => undefined}
        wsRef={{ current: null }}
        setSearchParams={() => undefined}
        setGenerationsOpen={(open: boolean) => {
          if (open) setGenerationsOpened(true)
        }}
        openAgentEditor={(detail: { agentId?: string }) => {
          setEditorAgentId(detail?.agentId || 'codey')
        }}
        navigateToPaletteAgent={() => undefined}
      />
      {editorAgentId ? (
        <div data-testid="proof-full-editor-requested" data-agent-id={editorAgentId} />
      ) : null}
      {generationsOpened ? <div data-testid="proof-generations-opened" /> : null}
    </div>
  )
}

export function Ia1447Proof() {
  const surface = useMemo(() => readSurface(), [])
  const [href, setHref] = useState(() =>
    typeof window === 'undefined' ? IA_1447_PROOF_PATH : window.location.href,
  )

  // Layout, not render. StrictMode drops the first render's hooks and then
  // replays this effect, which puts the stub back before child fetches.
  useLayoutEffect(() => installProofFetch(), [])

  useEffect(() => {
    setHref(window.location.href)
    document.title = `Operating Swarm · #1447 ${surface} · ${IA_1447_PROOF_PATH}`
  }, [surface])

  const client = useMemo(
    () => new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } }),
    [],
  )

  return (
    <QueryClientProvider client={client}>
      <div
        className="min-h-screen bg-base-100 text-base-content"
        data-testid="ia-1447-proof"
        data-proof-surface={surface}
      >
        <ProofAddressBar href={href} />
        <p className="px-3 py-2 text-sm" data-testid="proof-caption-1447">
          {surface === 'computer'
            ? 'Computer Control · Routines + Test schedule only — no Agent tab'
            : 'Live ChatHeader avatar opens AgentConfigSidepane — pencil and right-click keep the full editor'}
        </p>
        <LiveChatHeader surface={surface} />
      </div>
    </QueryClientProvider>
  )
}

export default Ia1447Proof
