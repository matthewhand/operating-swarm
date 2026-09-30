/**
 * Vite/Playwright harness for #1715 visual proof + geometry.
 *
 * Unique route:
 *   `/__proof__/badge-pill-1715?theme=dark|light&folder=unset|bound&role=off|on`
 * In-frame URL chrome repeats `window.location.href`, so every capture carries a
 * distinct path without secrets.
 *
 * `folder=unset&role=off` is the state the ticket is about: no working folder
 * bound, so the label column holds exactly ONE row. `folder=bound&role=off` is
 * the control: the same seat with a working folder, which adds the path row and
 * therefore makes it multi-line. `role=on` adds the `role@rig` badge on top of
 * either, so the capture can also show that the multi-line matrix (#1706) is
 * untouched.
 *
 * All four states mount the LIVE `ChatHeader` with the same props except the two
 * that are the claim, which is what makes them comparable: any difference in
 * vertical placement is a layout claim about the badge, not about two different
 * harnesses.
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
import { BADGE_PILL_PROOF_1715_PATH } from './proofPaths'

export { BADGE_PILL_PROOF_1715_PATH } from './proofPaths'

export type Proof1715Folder = 'unset' | 'bound'
export type Proof1715Theme = 'dark' | 'light'

const BOUND_SUBTITLE = '/srv/swarm/workspaces/engineering — branch: fix/1715'
const BOUND_SUBTITLE_DISPLAY = '.../engineering — branch: fix/1715'

function readFolder(): Proof1715Folder {
  return new URLSearchParams(window.location.search).get('folder') === 'bound' ? 'bound' : 'unset'
}

function readTheme(): Proof1715Theme {
  return new URLSearchParams(window.location.search).get('theme') === 'light' ? 'light' : 'dark'
}

function readRole(): boolean {
  return new URLSearchParams(window.location.search).get('role') === 'on'
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

type ProofFetchWindow = Window & {
  __proof1715Restore?: () => void
}

function installProofFetch(): () => void {
  const marked = window as ProofFetchWindow
  if (marked.__proof1715Restore) return marked.__proof1715Restore
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
    if (marked.__proof1715Restore === restore) {
      delete marked.__proof1715Restore
    }
  }
  marked.__proof1715Restore = restore
  window.fetch = wrapped
  return restore
}

function ProofAddressBar({ href }: { href: string }) {
  return (
    <header
      data-testid="proof-chrome-1715"
      className="border-b border-base-300 bg-base-200 px-3 py-2"
    >
      <div className="mb-1 text-xs font-medium text-base-content/70">
        Operating Swarm — Issue #1715 proof
      </div>
      <div
        className="flex items-center gap-2 rounded-box border border-base-300 bg-base-100 px-3 py-1.5"
        data-testid="proof-url-bar-1715"
        aria-label="Proof URL bar"
      >
        <span className="flex gap-1" aria-hidden="true">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-error/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-warning/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-success/70" />
        </span>
        <span className="truncate font-mono text-xs" data-testid="proof-url-1715">
          {href}
        </span>
      </div>
    </header>
  )
}

function LiveChatHeader({ folder, role }: { folder: Proof1715Folder; role: boolean }) {
  const bound = folder === 'bound'
  return (
    <div data-testid="proof-1715-badge" data-proof-folder={folder} data-proof-role={role ? 'on' : 'off'}>
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
        showHeaderRole={role}
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
        // #1715: the only props that differ between the proof states. `role=off`
        // keeps the label column to a single row so the claim is about the lone
        // label, not about the role badge's share of the column.
        workspaceFolderEditable
        workspaceSubtitle={bound ? BOUND_SUBTITLE : ''}
        workspaceSubtitleDisplay={bound ? BOUND_SUBTITLE_DISPLAY : ''}
      />
    </div>
  )
}

export function BadgePillProof1715() {
  const folder = useMemo(() => readFolder(), [])
  const theme = useMemo(() => readTheme(), [])
  const role = useMemo(() => readRole(), [])
  const [href, setHref] = useState(() =>
    typeof window === 'undefined' ? BADGE_PILL_PROOF_1715_PATH : window.location.href,
  )

  useLayoutEffect(() => installProofFetch(), [])

  useEffect(() => {
    const previous = document.documentElement.dataset.theme
    document.documentElement.dataset.theme = theme
    document.documentElement.style.colorScheme = theme
    setHref(window.location.href)
    document.title = `Operating Swarm — #1715 ${theme} ${folder} role=${role ? 'on' : 'off'} — ${BADGE_PILL_PROOF_1715_PATH}`
    return () => {
      if (previous) document.documentElement.dataset.theme = previous
      else delete document.documentElement.dataset.theme
    }
  }, [theme, folder, role])

  const client = useMemo(
    () => new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } }),
    [],
  )

  const rows = (role ? 1 : 0) + 1 + (folder === 'bound' ? 1 : 0)

  return (
    <QueryClientProvider client={client}>
      <div
        className="min-h-screen bg-base-100 text-base-content"
        data-testid="badge-pill-1715-proof"
        data-proof-theme={theme}
        data-proof-folder={folder}
        data-proof-role={role ? 'on' : 'off'}
        data-proof-rows={rows}
      >
        <ProofAddressBar href={href} />
        <p className="px-3 py-2 text-sm" data-testid="proof-caption-1715">
          {folder === 'unset' && !role
            ? 'No working folder bound, no role badge — the badge carries ONE label, and that lone label is vertically centred in the pill, not top- or bottom-biased as if a second line were present.'
            : folder === 'bound' && !role
              ? 'Working folder bound — the path is the second row, so the badge is multi-line exactly as #1706 designed it. Unchanged by #1715.'
              : role
                ? 'Role badge on — the `role@rig` badge is the second row and the label matrix (#1706) is unchanged by #1715.'
                : 'Badge state.'}
        </p>
        <LiveChatHeader folder={folder} role={role} />
      </div>
    </QueryClientProvider>
  )
}

export default BadgePillProof1715
