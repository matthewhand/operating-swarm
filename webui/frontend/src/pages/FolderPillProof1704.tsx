/**
 * Vite/Playwright harness for #1704 visual proof + geometry.
 *
 * Unique route:
 *   `/__proof__/folder-pill-1704?theme=dark|light&folder=unset|bound`
 * In-frame URL chrome repeats `window.location.href`, so every capture carries a
 * distinct path without secrets.
 *
 * `folder=unset` is the state the ticket is about: no working folder bound, and
 * the seat can bind one — the only state in which the folder affordance exists
 * at all. `folder=bound` is the control: a real path subtitle, so the "nothing
 * bound" icon is gone and the pill shows a name-only bottom label.
 *
 * Both states mount the LIVE `ChatHeader` with the same props, which is what
 * makes the two heights comparable: any difference in pill height between them
 * is a layout claim about the affordance, not about two different harnesses.
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
import { FOLDER_PILL_PROOF_1704_PATH } from './proofPaths'

export { FOLDER_PILL_PROOF_1704_PATH } from './proofPaths'

export type Proof1704Folder = 'unset' | 'bound'
export type Proof1704Theme = 'dark' | 'light'

const BOUND_SUBTITLE = '/srv/swarm/workspaces/engineering — branch: feat/1704'

function readFolder(): Proof1704Folder {
  return new URLSearchParams(window.location.search).get('folder') === 'bound' ? 'bound' : 'unset'
}

function readTheme(): Proof1704Theme {
  return new URLSearchParams(window.location.search).get('theme') === 'light' ? 'light' : 'dark'
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

type ProofFetchWindow = Window & {
  __proof1704Restore?: () => void
}

function installProofFetch(): () => void {
  const marked = window as ProofFetchWindow
  if (marked.__proof1704Restore) return marked.__proof1704Restore
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
    if (marked.__proof1704Restore === restore) {
      delete marked.__proof1704Restore
    }
  }
  marked.__proof1704Restore = restore
  window.fetch = wrapped
  return restore
}

function ProofAddressBar({ href }: { href: string }) {
  return (
    <header
      data-testid="proof-chrome-1704"
      className="border-b border-base-300 bg-base-200 px-3 py-2"
    >
      <div className="mb-1 text-xs font-medium text-base-content/70">
        Operating Swarm — Issue #1704 proof
      </div>
      <div
        className="flex items-center gap-2 rounded-box border border-base-300 bg-base-100 px-3 py-1.5"
        data-testid="proof-url-bar-1704"
        aria-label="Proof URL bar"
      >
        <span className="flex gap-1" aria-hidden="true">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-error/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-warning/70" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-success/70" />
        </span>
        <span className="truncate font-mono text-xs" data-testid="proof-url-1704">
          {href}
        </span>
      </div>
    </header>
  )
}

function LiveChatHeader({ folder }: { folder: Proof1704Folder }) {
  const bound = folder === 'bound'
  return (
    <div data-testid="proof-1704-pill" data-proof-folder={folder}>
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
        // #1704: the only two props that differ between the two proof states.
        workspaceFolderEditable
        workspaceSubtitle={bound ? BOUND_SUBTITLE : ''}
        workspaceSubtitleDisplay={bound ? '.../engineering — branch: feat/1704' : ''}
      />
    </div>
  )
}

export function FolderPillProof1704() {
  const folder = useMemo(() => readFolder(), [])
  const theme = useMemo(() => readTheme(), [])
  const [href, setHref] = useState(() =>
    typeof window === 'undefined' ? FOLDER_PILL_PROOF_1704_PATH : window.location.href,
  )

  useLayoutEffect(() => installProofFetch(), [])

  useEffect(() => {
    const previous = document.documentElement.dataset.theme
    document.documentElement.dataset.theme = theme
    document.documentElement.style.colorScheme = theme
    setHref(window.location.href)
    document.title = `Operating Swarm — #1704 ${theme} ${folder} — ${FOLDER_PILL_PROOF_1704_PATH}`
    return () => {
      if (previous) document.documentElement.dataset.theme = previous
      else delete document.documentElement.dataset.theme
    }
  }, [theme, folder])

  const client = useMemo(
    () => new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } }),
    [],
  )

  return (
    <QueryClientProvider client={client}>
      <div
        className="min-h-screen bg-base-100 text-base-content"
        data-testid="folder-pill-1704-proof"
        data-proof-theme={theme}
        data-proof-folder={folder}
      >
        <ProofAddressBar href={href} />
        <p className="px-3 py-2 text-sm" data-testid="proof-caption-1704">
          {folder === 'unset'
            ? 'No working folder bound — Select folder is an icon in the pill’s right-aligned action cluster, beside the pencil. Same row, same density, no second line.'
            : 'Working folder bound — the path is the bottom label in the name column, and the “nothing bound” icon is gone.'}
        </p>
        <LiveChatHeader folder={folder} />
      </div>
    </QueryClientProvider>
  )
}

export default FolderPillProof1704
