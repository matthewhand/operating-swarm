/**
 * Vite/Playwright harness for #1676 visual proof.
 *
 * Unique route: `/__proof__/agent-pill-1676?theme=dark|light&surface=pill|edit`
 * In-frame URL chrome repeats `window.location.href` so each screenshot
 * carries a distinct path without secrets.
 *
 * The navbar is the live `ChatHeader` ChatPage mounts. The centered agent
 * avatar+name pill opens `AgentConfigSidepane` on click (same pane the
 * Success criteria name as the edit-agent surface).
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
import { AGENT_PILL_PROOF_1676_PATH } from './proofPaths'

export { AGENT_PILL_PROOF_1676_PATH } from './proofPaths'

export type Proof1676Surface = 'pill' | 'edit'
export type Proof1676Theme = 'dark' | 'light'

function readSurface(): Proof1676Surface {
  return new URLSearchParams(window.location.search).get('surface') === 'edit' ? 'edit' : 'pill'
}

function readTheme(): Proof1676Theme {
  return new URLSearchParams(window.location.search).get('theme') === 'light' ? 'light' : 'dark'
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

type ProofFetchWindow = Window & {
  __proof1676Restore?: () => void
}

function installProofFetch(): () => void {
  const marked = window as ProofFetchWindow
  if (marked.__proof1676Restore) return marked.__proof1676Restore
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
    if (marked.__proof1676Restore === restore) {
      delete marked.__proof1676Restore
    }
  }
  marked.__proof1676Restore = restore
  window.fetch = wrapped
  return restore
}

function ProofAddressBar({ href }: { href: string }) {
  return (
    <header
      data-testid="proof-chrome-1676"
      className="border-b border-base-300 bg-base-200 px-3 py-2"
    >
      <div className="mb-1 text-xs font-medium text-base-content/70">
        Operating Swarm — Issue #1676 proof
      </div>
      <div
        className="flex items-center gap-2 rounded-box border border-base-300 bg-base-100 px-3 py-1.5"
        data-testid="proof-url-bar-1676"
        aria-label="Proof URL bar"
      >
        <span className="flex gap-1" aria-hidden="true">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-error/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-warning/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-success/70" />
        </span>
        <span className="truncate font-mono text-xs" data-testid="proof-url-1676">
          {href}
        </span>
      </div>
    </header>
  )
}

function LiveChatHeader({ surface }: { surface: Proof1676Surface }) {
  useEffect(() => {
    if (surface !== 'edit') return
    // Click the centered floating pill — Success says this opens the edit pane.
    const t = window.setTimeout(() => {
      document
        .querySelector<HTMLElement>('[data-testid="selected-agent-header"]')
        ?.click()
    }, 80)
    return () => window.clearTimeout(t)
  }, [surface])

  return (
    <div data-testid={surface === 'edit' ? 'proof-1676-edit' : 'proof-1676-pill'}>
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
        setGenerationsOpen={() => undefined}
        openAgentEditor={() => undefined}
        navigateToPaletteAgent={() => undefined}
      />
    </div>
  )
}

export function AgentPillProof1676() {
  const surface = useMemo(() => readSurface(), [])
  const theme = useMemo(() => readTheme(), [])
  const [href, setHref] = useState(() =>
    typeof window === 'undefined' ? AGENT_PILL_PROOF_1676_PATH : window.location.href,
  )

  useLayoutEffect(() => installProofFetch(), [])

  useEffect(() => {
    const previous = document.documentElement.dataset.theme
    document.documentElement.dataset.theme = theme
    document.documentElement.style.colorScheme = theme
    setHref(window.location.href)
    document.title = `Operating Swarm — #1676 ${theme} ${surface} — ${AGENT_PILL_PROOF_1676_PATH}`
    return () => {
      if (previous) document.documentElement.dataset.theme = previous
      else delete document.documentElement.dataset.theme
    }
  }, [theme, surface])

  const client = useMemo(
    () => new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } }),
    [],
  )

  return (
    <QueryClientProvider client={client}>
      <div
        className="min-h-screen bg-base-100 text-base-content"
        data-testid="agent-pill-1676-proof"
        data-proof-surface={surface}
        data-proof-theme={theme}
      >
        <ProofAddressBar href={href} />
        <p className="px-3 py-2 text-sm" data-testid="proof-caption-1676">
          {surface === 'edit'
            ? 'Centered agent pill clicked — AgentConfigSidepane open (edit-agent)'
            : 'Centered floating agent avatar+name pill in the chat header'}
        </p>
        <LiveChatHeader surface={surface} />
      </div>
    </QueryClientProvider>
  )
}

export default AgentPillProof1676